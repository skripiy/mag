"""Оцінка якості та продуктивності системи (Розділ 4).

Проганяє розмічений датасет звернень (data/requests/hotline_requests.jsonl)
через складові системи й рахує метрики, підкріплені розміткою:

  • Пошук (Ф2): recall@k, precision@1, MRR за expected_doc — по темах і загалом.
  • Маршрутизація наміру: точність визначення гілки «інструмент/RAG»
    (за category=status_lookup) — precision / recall / F1.
  • Анонімізація (НФ1): recall на зверненнях із PII та частка хибних
    спрацювань на pii-негативах (числа, схожі на PII, але ним не є).
  • Латентність пошуку.

За прапорцем --full додатково виконується повний конвеєр (з генерацією):
  • Коректність відмови (faithfulness): частка відмов на зверненнях, де
    відповіді в базі немає (out_of_scope / ambiguous / faithfulness_trap),
    проти зверненнь, на які відповідь є.
  • Наскрізна латентність опрацювання.

Запуск (усередині контейнера застосунку):
    docker compose exec app python -m app.evaluation
    docker compose exec app python -m app.evaluation --full
    docker compose exec app python -m app.evaluation --full --limit 20
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass, field

from app.agent import _looks_like_status_query
from app.agent import answer as agent_answer
from app.anonymize import Anonymizer
from app.config import settings
from app.generation import NO_CONTEXT_ANSWER
from app.retrieval import search_text

# Категорії, для яких правильною поведінкою є відмова / уточнення (відповіді
# в базі знань немає або запит некоректний).
REFUSE_CATEGORIES = {"out_of_scope", "ambiguous", "faithfulness_trap"}

# Мовні маркери контрольованої відмови / уточнення у відповіді.
REFUSAL_MARKERS = (
    "недостатньо",
    "немає інформації",
    "не знайдено",
    "не можу надати",
    "не маю",
    "уточн",
    "вкажіть",
    "перевірте номер",
    "зверніться до оператора",
    NO_CONTEXT_ANSWER[:30],
)


def _is_refusal(text: str) -> bool:
    low = (text or "").lower()
    return any(m.lower() in low for m in REFUSAL_MARKERS)


def load_dataset(path: str) -> list[dict]:
    items: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


# --------------------------------------------------------------------------- #
# Пошук (Ф2)                                                                   #
# --------------------------------------------------------------------------- #
@dataclass
class RetrievalStats:
    n: int = 0
    hits: int = 0          # expected_doc у top-k
    p_at_1: int = 0        # expected_doc на 1-й позиції
    mrr_sum: float = 0.0
    latencies_ms: list[float] = field(default_factory=list)

    def add(self, rank: int | None, latency_ms: float) -> None:
        self.n += 1
        self.latencies_ms.append(latency_ms)
        if rank is not None:
            self.hits += 1
            self.mrr_sum += 1.0 / rank
            if rank == 1:
                self.p_at_1 += 1


async def eval_retrieval(items: list[dict]) -> dict:
    overall = RetrievalStats()
    per_cat: dict[str, RetrievalStats] = defaultdict(RetrievalStats)
    subset = [it for it in items if it.get("expected_doc")]
    for it in subset:
        expected = it["expected_doc"]
        t0 = time.perf_counter()
        chunks = await search_text(it["text"])
        latency_ms = (time.perf_counter() - t0) * 1000
        # Порядок документів за спаданням релевантності (без повторів).
        seen: list[str] = []
        for c in chunks:
            if c.document_title not in seen:
                seen.append(c.document_title)
        rank = (seen.index(expected) + 1) if expected in seen else None
        overall.add(rank, latency_ms)
        per_cat[it["category"]].add(rank, latency_ms)
    return {"overall": overall, "per_cat": dict(per_cat), "n_subset": len(subset)}


# --------------------------------------------------------------------------- #
# Маршрутизація наміру (RAG vs інструмент)                                     #
# --------------------------------------------------------------------------- #
def eval_routing(items: list[dict]) -> dict:
    tp = fp = tn = fn = 0
    errors: list[dict] = []
    for it in items:
        actual_tool = it["category"] == "status_lookup"
        pred_tool = _looks_like_status_query(it["text"])
        if actual_tool and pred_tool:
            tp += 1
        elif actual_tool and not pred_tool:
            fn += 1
            errors.append({"id": it["id"], "type": "missed_tool", "text": it["text"]})
        elif not actual_tool and pred_tool:
            fp += 1
            errors.append({"id": it["id"], "type": "false_tool", "text": it["text"]})
        else:
            tn += 1
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    acc = (tp + tn) / len(items) if items else 0.0
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "precision": prec,
            "recall": rec, "f1": f1, "accuracy": acc, "errors": errors}


# --------------------------------------------------------------------------- #
# Анонімізація (НФ1)                                                           #
# --------------------------------------------------------------------------- #
def eval_anonymization(items: list[dict]) -> dict:
    # Базовий (regex) рівень — детермінований і не потребує зовнішніх моделей.
    anon = Anonymizer(use_presidio=False)

    pii = [it for it in items if it.get("has_pii")]
    neg = [it for it in items if "pii-negative" in (it.get("note") or "")]
    clean = [it for it in items
             if not it.get("has_pii") and "pii-negative" not in (it.get("note") or "")]

    def masked(text: str) -> int:
        _, ents = anon.anonymize(text)
        return len(ents)

    pii_hit = sum(1 for it in pii if masked(it["text"]) > 0)
    neg_fp = sum(1 for it in neg if masked(it["text"]) > 0)
    clean_fp = sum(1 for it in clean if masked(it["text"]) > 0)

    neg_examples = [it["id"] for it in neg if masked(it["text"]) > 0]
    return {
        "presidio": anon.presidio_enabled,
        "pii_n": len(pii), "pii_recall": pii_hit / len(pii) if pii else 0.0,
        "neg_n": len(neg), "neg_fp": neg_fp,
        "neg_fp_rate": neg_fp / len(neg) if neg else 0.0,
        "neg_fp_ids": neg_examples,
        "clean_n": len(clean), "clean_fp": clean_fp,
        "clean_fp_rate": clean_fp / len(clean) if clean else 0.0,
    }


# --------------------------------------------------------------------------- #
# Відповіді: коректність відмови + наскрізна латентність (--full)             #
# --------------------------------------------------------------------------- #
async def eval_answers(items: list[dict]) -> dict:
    refuse_total = refuse_ok = 0
    answer_total = answer_wrong_refuse = 0
    latencies_ms: list[float] = []
    per_cat_lat: dict[str, list[float]] = defaultdict(list)
    failed = 0
    for it in items:
        t0 = time.perf_counter()
        try:
            result = await agent_answer(it["text"])
        except Exception as exc:  # noqa: BLE001
            # Напр. модель без підтримки function calling на status-запиті —
            # не зриваємо весь прогін, а фіксуємо збій і рухаємось далі.
            failed += 1
            print(f"[eval] пропущено {it['id']} ({it['category']}): {type(exc).__name__}: {str(exc)[:80]}")
            continue
        latency_ms = (time.perf_counter() - t0) * 1000
        latencies_ms.append(latency_ms)
        per_cat_lat[it["category"]].append(latency_ms)
        refused = _is_refusal(result.answer)
        if it["category"] in REFUSE_CATEGORIES:
            refuse_total += 1
            if refused:
                refuse_ok += 1
        elif it.get("expected_doc"):  # звернення, на яке відповідь у базі є
            answer_total += 1
            if refused:
                answer_wrong_refuse += 1
    return {
        "refuse_total": refuse_total,
        "refuse_ok": refuse_ok,
        "refuse_rate": refuse_ok / refuse_total if refuse_total else 0.0,
        "answer_total": answer_total,
        "answer_wrong_refuse": answer_wrong_refuse,
        "answer_false_refuse_rate": answer_wrong_refuse / answer_total if answer_total else 0.0,
        "failed": failed,
        "latencies_ms": latencies_ms,
        "per_cat_lat": {k: v for k, v in per_cat_lat.items()},
    }


# --------------------------------------------------------------------------- #
# Розгортка по порогу релевантності min_score (без генерації)                 #
# --------------------------------------------------------------------------- #
# Контрольована відмова спрацьовує, коли жоден фрагмент не досягає порогу.
# Тут для кожного звернення виконуємо пошук БЕЗ порогу (одноразово), а тоді
# перевіряємо ефект різних порогів: скільки позатематичних звернень поріг
# змусить відхилити (добре) проти скількох релевантних він відкине (погано).
async def eval_min_score_sweep(items: list[dict], thresholds: list[float]) -> dict:
    # категорії, які поріг здатен відхилити (слабкі/відсутні збіги)
    oos = [it for it in items if it["category"] in ("out_of_scope", "ambiguous")]
    answerable = [it for it in items
                  if it.get("expected_doc") and it["category"] not in REFUSE_CATEGORIES]
    ftrap = [it for it in items if it["category"] == "faithfulness_trap"]

    async def scored(subset: list[dict]) -> list[tuple[float, str | None, list[str]]]:
        out = []
        for it in subset:
            chunks = await search_text(it["text"], min_score=0.0)  # без порогу
            max_s = max((c.score for c in chunks), default=0.0)
            titles = [c.document_title for c in chunks]
            out.append((max_s, it.get("expected_doc"), titles, chunks))
        return out

    oos_s = await scored(oos)
    ans_s = await scored(answerable)
    ft_s = await scored(ftrap)

    rows = []
    for T in thresholds:
        # позатематичні: відхилено, якщо max_score < T
        oos_refused = sum(1 for m, *_ in oos_s if m < T)
        # релевантні: відхилено помилково, якщо max_score < T
        ans_refused = sum(1 for m, *_ in ans_s if m < T)
        # релевантні: expected_doc усе ще у видачі з оцінкою >= T
        ans_kept = 0
        for m, exp, titles, chunks in ans_s:
            kept = [c.document_title for c in chunks if c.score >= T]
            if exp in kept:
                ans_kept += 1
        ft_refused = sum(1 for m, *_ in ft_s if m < T)
        rows.append({
            "threshold": T,
            "oos_refuse_rate": oos_refused / len(oos) if oos else 0.0,
            "ans_recall": ans_kept / len(answerable) if answerable else 0.0,
            "ans_false_refuse_rate": ans_refused / len(answerable) if answerable else 0.0,
            "ftrap_refuse_rate": ft_refused / len(ftrap) if ftrap else 0.0,
        })
    return {"n_oos": len(oos), "n_answerable": len(answerable), "n_ftrap": len(ftrap),
            "rows": rows}


# --------------------------------------------------------------------------- #
# Звіт                                                                         #
# --------------------------------------------------------------------------- #
def _pct(x: float) -> str:
    return f"{x * 100:5.1f}%"


def _lat_summary(vals: list[float]) -> str:
    if not vals:
        return "—"
    s = sorted(vals)
    p50 = statistics.median(s)
    p95 = s[min(len(s) - 1, int(0.95 * len(s)))]
    return f"сер={statistics.mean(s):.0f} мс · p50={p50:.0f} мс · p95={p95:.0f} мс · max={s[-1]:.0f} мс"


def print_report(res: dict) -> None:
    print("\n" + "=" * 64)
    print(f"ОЦІНКА СИСТЕМИ — {res['dataset']}  (звернень: {res['n_total']})")
    print(f"Модель: {settings.llm_model} · ембединги: {settings.embed_model} · top_k={settings.top_k} · min_score={settings.min_score}")
    print("=" * 64)

    r = res["retrieval"]["overall"]
    print(f"\n[1] ПОШУК У БАЗІ ЗНАНЬ (Ф2) — на {res['retrieval']['n_subset']} зверненнях з expected_doc")
    print(f"    recall@{settings.top_k}: {_pct(r.hits / r.n)}   "
          f"precision@1: {_pct(r.p_at_1 / r.n)}   MRR: {r.mrr_sum / r.n:.3f}")
    print(f"    латентність пошуку: {_lat_summary(r.latencies_ms)}")
    print("    за темами:")
    for cat, st in sorted(res["retrieval"]["per_cat"].items()):
        print(f"      {cat:24} n={st.n:2}  recall@{settings.top_k}={_pct(st.hits / st.n)}  "
              f"p@1={_pct(st.p_at_1 / st.n)}  MRR={st.mrr_sum / st.n:.3f}")

    rt = res["routing"]
    print(f"\n[2] МАРШРУТИЗАЦІЯ НАМІРУ (гілка «інструмент» vs RAG)")
    print(f"    accuracy: {_pct(rt['accuracy'])}   precision: {_pct(rt['precision'])}   "
          f"recall: {_pct(rt['recall'])}   F1: {rt['f1']:.3f}")
    print(f"    TP={rt['tp']} FP={rt['fp']} TN={rt['tn']} FN={rt['fn']}")
    if rt["errors"]:
        print("    помилки маршрутизації:")
        for e in rt["errors"]:
            print(f"      [{e['type']}] {e['id']}: {e['text'][:60]}")

    a = res["anonymization"]
    print(f"\n[3] АНОНІМІЗАЦІЯ (НФ1) — рівень: {'regex+Presidio' if a['presidio'] else 'regex'}")
    print(f"    recall на зверненнях з PII: {_pct(a['pii_recall'])}  (n={a['pii_n']})")
    print(f"    хибні спрацювання на pii-негативах: {a['neg_fp']}/{a['neg_n']}  "
          f"({_pct(a['neg_fp_rate'])})  {a['neg_fp_ids']}")
    print(f"    хибні спрацювання на «чистих» зверненнях: {a['clean_fp']}/{a['clean_n']}  "
          f"({_pct(a['clean_fp_rate'])})")

    if "answers" in res:
        an = res["answers"]
        print(f"\n[4] ВІДПОВІДІ ТА ЛАТЕНТНІСТЬ (повний конвеєр)")
        print(f"    коректна відмова (out_of_scope/ambiguous/faithfulness_trap): "
              f"{an['refuse_ok']}/{an['refuse_total']}  ({_pct(an['refuse_rate'])})")
        print(f"    хибна відмова на відповідних зверненнях: "
              f"{an['answer_wrong_refuse']}/{an['answer_total']}  ({_pct(an['answer_false_refuse_rate'])})")
        print(f"    наскрізна латентність: {_lat_summary(an['latencies_ms'])}")
        if an.get("failed"):
            print(f"    пропущено (збій генерації, напр. без tool-calling): {an['failed']}")

    if "sweep" in res:
        sw = res["sweep"]
        print(f"\n[5] РОЗГОРТКА ПО ПОРОГУ min_score (рівень пошуку, без генерації)")
        print(f"    позатематичні (out_of_scope+ambiguous, n={sw['n_oos']}): відхилено порогом")
        print(f"    релевантні (n={sw['n_answerable']}): recall (не втрачено) / хибна відмова")
        print(f"    faithfulness-пастки (n={sw['n_ftrap']}): відхилено порогом (їх поріг НЕ ловить)")
        print(f"    {'поріг':>6}  {'відмова OOS':>12}  {'recall релев.':>13}  {'хибна відмова':>13}  {'пастки':>8}")
        for row in sw["rows"]:
            print(f"    {row['threshold']:>6.2f}  {_pct(row['oos_refuse_rate']):>12}  "
                  f"{_pct(row['ans_recall']):>13}  {_pct(row['ans_false_refuse_rate']):>13}  "
                  f"{_pct(row['ftrap_refuse_rate']):>8}")
    print("\n" + "=" * 64 + "\n")


def _to_serializable(res: dict) -> dict:
    out = dict(res)
    r = res["retrieval"]["overall"]
    out["retrieval"] = {
        "n_subset": res["retrieval"]["n_subset"],
        "overall": {"n": r.n, "recall_at_k": r.hits / r.n, "p_at_1": r.p_at_1 / r.n,
                    "mrr": r.mrr_sum / r.n, "latency_ms": _lat_summary(r.latencies_ms)},
        "per_cat": {c: {"n": s.n, "recall_at_k": s.hits / s.n, "p_at_1": s.p_at_1 / s.n,
                        "mrr": s.mrr_sum / s.n}
                    for c, s in res["retrieval"]["per_cat"].items()},
    }
    if "answers" in res:
        an = dict(res["answers"])
        an.pop("latencies_ms", None)
        an.pop("per_cat_lat", None)
        an["latency_ms"] = _lat_summary(res["answers"]["latencies_ms"])
        out["answers"] = an
    return out


DEFAULT_THRESHOLDS = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]


async def run(dataset: str, full: bool, limit: int | None, sweep: bool) -> dict:
    items = load_dataset(dataset)
    if limit:
        items = items[:limit]
    res: dict = {"dataset": dataset, "n_total": len(items)}
    res["retrieval"] = await eval_retrieval(items)
    res["routing"] = eval_routing(items)
    res["anonymization"] = eval_anonymization(items)
    if full:
        res["answers"] = await eval_answers(items)
    if sweep:
        res["sweep"] = await eval_min_score_sweep(items, DEFAULT_THRESHOLDS)
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description="Оцінка системи (Розділ 4)")
    ap.add_argument("--dataset", default="data/requests/hotline_requests.jsonl")
    ap.add_argument("--full", action="store_true",
                    help="виконати повний конвеєр із генерацією (повільно)")
    ap.add_argument("--sweep", action="store_true",
                    help="розгортка по порогу min_score (рівень пошуку, швидко)")
    ap.add_argument("--limit", type=int, default=None, help="обмежити кількість звернень")
    ap.add_argument("--out", default=None, help="шлях для JSON-звіту")
    args = ap.parse_args()

    res = asyncio.run(run(args.dataset, args.full, args.limit, args.sweep))
    print_report(res)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(_to_serializable(res), f, ensure_ascii=False, indent=2)
        print(f"[eval] JSON-звіт збережено: {args.out}")


if __name__ == "__main__":
    main()

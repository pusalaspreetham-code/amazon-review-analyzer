"""Streamlit rendering helpers. All scraped text is escaped before display."""
from __future__ import annotations

import html
import re
from typing import List, Optional, Tuple

import pandas as pd
import streamlit as st

from . import config
from .data import Product, Review
from .pipeline import Analysis
from .sentiment import LABELS, Prediction

NA = "Not available"
TONE_ICON = {"good": "🟢", "mixed": "🟡", "bad": "🔴", "info": "ℹ️"}
SENTIMENT_ICON = {"Positive": "🟢", "Neutral": "🟡", "Negative": "🔴"}


def md_escape(text: str) -> str:
    """Escape markdown/LaTeX so review text is shown literally."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!$<>|~:])", r"\\\1", text)


def _money(value: Optional[float]) -> str:
    return f"₹{value:,.0f}" if value is not None else NA


# ------------------------------------------------------------------------ verdict
def render_verdict(analysis: Analysis) -> None:
    from .insights import headline
    rec = analysis.recommendation
    color = config.VERDICT_COLORS[rec.verdict]
    score = f"{rec.score:.0f}" if rec.score is not None else "N/A"
    left, right = st.columns([1, 2])
    with left:
        st.markdown(
            f"""<div style="border-left:6px solid {color};padding:16px 20px;border-radius:8px;
                background:rgba(128,128,128,.08)">
                <div style="font-size:14px;opacity:.7">Product Recommendation Score</div>
                <div style="font-size:52px;font-weight:700;line-height:1.1">{score}
                    <span style="font-size:22px;opacity:.6">/ 100</span></div>
                <div style="font-size:22px;font-weight:600;color:{color}">{html.escape(rec.verdict)}</div>
                <div style="font-size:13px;opacity:.7;margin-top:6px">{html.escape(headline(rec))}</div>
                <div style="font-size:12px;opacity:.55;margin-top:8px">Data coverage: {rec.coverage:.0%}</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with right:
        st.subheader("Why this recommendation?")
        for reason in analysis.reasons:
            st.markdown(f"{TONE_ICON[reason.tone]} {reason.text}")


# ------------------------------------------------------------------------ product
def render_product(product: Product) -> None:
    st.markdown(f"#### {md_escape(product.name)}")
    if product.url:
        st.markdown(f"[Open on Amazon.in]({product.url})")
    if product.category:
        st.caption(md_escape(product.category))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Price", _money(product.price))
    c2.metric("List price (MRP)", _money(product.original_price))
    discount = product.effective_discount
    c3.metric("Discount", f"{discount:.0f}%" if discount is not None else NA)
    c4.metric("Product rating", f"{product.rating:.1f} / 5" if product.rating is not None else NA)

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Total reviews / ratings", f"{product.total_reviews:,}" if product.total_reviews else NA)
    c6.metric("Seller rating", f"{product.seller_rating:.1f} / 5" if product.seller_rating is not None else NA)
    c7.metric("Seller", product.seller_name or NA)
    c8.metric("Fulfilment", product.fulfillment or NA)

    st.markdown("**Star distribution**")
    if product.star_counts:
        total = sum(product.star_counts.values())
        df = pd.DataFrame({
            "Stars": [f"{s} ★" for s in range(5, 0, -1)],
            "Reviews": [product.star_counts[s] for s in range(5, 0, -1)],
            "Share": [f"{product.star_counts[s] / total:.0%}" for s in range(5, 0, -1)],
        })
        st.bar_chart(df.set_index("Stars")["Reviews"], horizontal=True)
        st.caption("Customer review counts per star level, as shown by Amazon's review filters. "
                   + " · ".join(f"{r.Stars}: {r.Share}" for r in df.itertuples()))
    else:
        st.info("The star distribution could not be read for this product.")


# ------------------------------------------------------------------------ sentiment
def render_sentiment(analysis: Analysis) -> None:
    s = analysis.summary
    if s.n == 0:
        st.info("No reviews were available to analyse.")
        return

    st.markdown("**Estimated sentiment across all reviews**" if s.weighted else "**Sentiment of collected reviews**")
    cols = st.columns(3)
    for col, label in zip(cols, LABELS):
        col.metric(f"{SENTIMENT_ICON[label]} {label}", f"{s.estimated_pct[label]:.0f}%")
    if s.weighted:
        st.caption(
            f"The scraper samples reviews from every star level, so sample percentages are re-weighted by "
            f"Amazon's real star distribution. Based on {s.n} analysed reviews."
        )
    for note in s.notes:
        st.caption(f"ℹ️ {note}")

    with st.expander("Raw sample (as collected, unweighted)"):
        st.dataframe(pd.DataFrame({
            "Sentiment": list(LABELS),
            "Reviews": [s.sample_counts[l] for l in LABELS],
            "Share of sample": [f"{s.sample_pct[l]:.0f}%" for l in LABELS],
        }), hide_index=True)

    st.markdown("**Prediction confidence**")
    m1, m2 = st.columns(2)
    m1.metric("Average confidence", f"{s.avg_confidence:.0%}")
    m2.metric(f"High-confidence predictions (≥{config.HIGH_CONFIDENCE:.0%})", f"{s.high_confidence_share:.0%}")
    bins = pd.DataFrame(s.confidence_bins, columns=["Confidence", "Reviews"]).set_index("Confidence")
    st.bar_chart(bins)


# ------------------------------------------------------------------------ feedback
def _review_card(review: Review, pred: Prediction) -> None:
    with st.container(border=True):
        stars = "★" * int(round(review.rating)) + "☆" * (5 - int(round(review.rating)))
        st.markdown(f"**{md_escape(review.title)}**  \n{stars}")
        st.markdown(md_escape(review.text))
        meta = [f"{SENTIMENT_ICON[pred.label]} {pred.label} ({pred.confidence:.0%} confidence)",
                f"{review.helpful_votes} found helpful"]
        if review.verified:
            meta.append("Verified purchase")
        if review.age_text:
            meta.append(md_escape(review.age_text))
        st.caption(" · ".join(meta))


def render_feedback(analysis: Analysis) -> None:
    pos, neg = st.columns(2)
    with pos:
        st.markdown("#### 👍 Important positive feedback")
        if analysis.top_positive:
            for review, pred in analysis.top_positive:
                _review_card(review, pred)
        else:
            st.info("No confidently positive reviews were found.")
    with neg:
        st.markdown("#### 👎 Important negative feedback")
        if analysis.top_negative:
            for review, pred in analysis.top_negative:
                _review_card(review, pred)
        else:
            st.info("No confidently negative reviews were found.")
    st.caption("Ranked by helpful votes, model confidence and level of detail.")


# ------------------------------------------------------------------------ breakdown
def render_breakdown(analysis: Analysis) -> None:
    rec = analysis.recommendation
    rows = [{
        "Factor": c.label,
        "Weight": f"{c.weight:.0%}",
        "Score": round(c.score) if c.available else None,
        "Status": "Used" if c.available else "Not available (excluded)",
        "Details": c.detail,
    } for c in rec.components]
    st.dataframe(
        pd.DataFrame(rows), hide_index=True,
        column_config={"Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d")},
    )
    st.caption(
        "Each available factor is scored 0-100 and combined using its weight. Missing factors are excluded and the "
        "remaining weights are re-normalised, so missing data is never treated as zero. "
        f"Verdict bands: {config.WORTH_CONSIDERING}+ Worth Considering · {config.CONSIDER_CAREFULLY}-{config.WORTH_CONSIDERING - 1} "
        f"Consider Carefully · {config.RISKY_PURCHASE}-{config.CONSIDER_CAREFULLY - 1} Risky Purchase · "
        f"below {config.RISKY_PURCHASE} Not Recommended."
    )
    if rec.verdict == config.VERDICT_INSUFFICIENT and rec.raw_score is not None:
        st.caption(f"Computed from only {rec.coverage:.0%} of the data ({rec.raw_score:.0f}/100), which is too little to base a verdict on.")


# ------------------------------------------------------------------------ all reviews
def render_reviews_table(analysis: Analysis) -> None:
    if not analysis.reviews:
        st.info("No reviews were collected.")
        return
    df = pd.DataFrame([{
        "Rating": r.rating,
        "Title": r.title,
        "Review": r.text,
        "Sentiment": p.label,
        "Confidence": round(p.confidence * 100),
        "Verified purchase": "Yes" if r.verified else "Not shown",
        "Helpful votes": r.helpful_votes,
        "Review age": r.age_text or NA,
    } for r, p in zip(analysis.reviews, analysis.predictions)])
    choice = st.selectbox("Filter by sentiment", ["All"] + list(LABELS))
    if choice != "All":
        df = df[df["Sentiment"] == choice]
    st.caption(f"{len(df)} reviews shown")
    st.dataframe(df, hide_index=True, column_config={
        "Confidence": st.column_config.NumberColumn("Confidence", format="%d%%"),
        "Review": st.column_config.TextColumn("Review", width="large"),
    })
    st.download_button("Download reviews as CSV", df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="analysed_reviews.csv", mime="text/csv")


def render_analysis(analysis: Analysis) -> None:
    for warning in analysis.warnings:
        st.warning(warning)
    render_verdict(analysis)
    st.divider()
    tabs = st.tabs(["Product details", "Sentiment", "Key feedback", "Score breakdown", "All reviews"])
    with tabs[0]:
        render_product(analysis.product)
    with tabs[1]:
        render_sentiment(analysis)
    with tabs[2]:
        render_feedback(analysis)
    with tabs[3]:
        render_breakdown(analysis)
    with tabs[4]:
        render_reviews_table(analysis)

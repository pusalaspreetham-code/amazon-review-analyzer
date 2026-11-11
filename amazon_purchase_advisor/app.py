"""Amazon Product Purchase Advisor - run with:  streamlit run app.py"""
import streamlit as st

from advisor import config
from advisor.pipeline import analyse
from advisor.scraper_service import friendly_error, parse_amazon_url, scrape
from advisor.sentiment import SentimentAnalyzer
from advisor.ui import render_analysis

st.set_page_config(page_title="Amazon Purchase Advisor", page_icon="🛒", layout="wide")


@st.cache_resource(show_spinner=False)
def load_analyzer() -> SentimentAnalyzer:
    return SentimentAnalyzer(config.MODEL_PATH)


def sidebar() -> tuple:
    with st.sidebar:
        st.header("Settings")
        per_star = st.slider(
            "Reviews to collect per star level", config.MIN_REVIEWS_PER_STAR, config.MAX_REVIEWS_PER_STAR,
            config.DEFAULT_REVIEWS_PER_STAR, step=5,
            help="Up to 5 star levels are scraped. More reviews give a better picture but take longer.")
        show_browser = st.checkbox(
            "Show browser window", value=True,
            help="Recommended. A visible browser is less likely to be blocked and lets you solve a CAPTCHA. "
                 "Turn off on servers without a display.")
        with st.expander("How the score works"):
            st.markdown(
                "\n".join([f"- **{k.title()}**: {v:.0%}" for k, v in config.WEIGHTS.items()])
                + "\n\nMissing data is excluded and the other weights are re-normalised. It is never counted as zero."
            )
    return per_star, not show_browser


def run_analysis(url: str, per_star: int, headless: bool):
    """Scrape + analyse. Returns an Analysis, or None after showing a clear error."""
    try:
        analyzer = load_analyzer()
    except Exception as exc:
        st.error(f"The sentiment model could not be loaded: {exc}")
        return None

    with st.status("Collecting product and review data from Amazon.in...", expanded=True) as status:
        log_box = st.empty()
        lines = []

        def on_log(line: str) -> None:
            lines.append(line)
            log_box.code("\n".join(lines[-6:]), language=None)

        outcome = scrape(url, per_star, headless, on_log=on_log)
        if not outcome.usable:
            status.update(label="Could not read the product", state="error")
            st.error(friendly_error(outcome))
            return None
        status.update(label="Analysing reviews...", state="running")
        analysis = analyse(outcome, analyzer)
        status.update(label="Analysis complete", state="complete", expanded=False)
    return analysis


def main() -> None:
    per_star, headless = sidebar()

    st.title("🛒 Amazon Product Purchase Advisor")
    st.caption("Paste an Amazon.in product link to get a data-driven buying recommendation from ratings, "
               "seller information and an analysis of customer reviews.")

    with st.form("url_form"):
        url = st.text_input("Amazon.in product URL", placeholder="https://www.amazon.in/dp/B0XXXXXXXX")
        submitted = st.form_submit_button("Analyse product", type="primary")

    if submitted:
        st.session_state.pop("analysis", None)
        clean_url, error = parse_amazon_url(url)
        if error:
            st.error(error)
        else:
            result = run_analysis(clean_url, per_star, headless)
            if result is not None:
                st.session_state["analysis"] = result

    analysis = st.session_state.get("analysis")
    if analysis is not None:
        render_analysis(analysis)
        st.caption(f"Analysed {analysis.analysed_at:%d %b %Y, %H:%M}. This is decision support based on public "
                   "review data, not a guarantee of product quality.")
    elif not submitted:
        st.info("Enter a product link above and click **Analyse product**. A scan usually takes 1-3 minutes.")


main()

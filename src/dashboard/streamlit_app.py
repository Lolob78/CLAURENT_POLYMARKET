"""Dashboard Streamlit pour monitoring du bot de trading."""
import streamlit as st
import pandas as pd
import subprocess
import sys
from src.risk.engine import risk


def run_dashboard():
    """Lance le dashboard Streamlit."""
    try:
        subprocess.run([
            sys.executable, "-m", "streamlit", "run",
            __file__,
            "--logger.level=error",
            "--client.showErrorDetails=false"
        ])
    except Exception as e:
        print(f"❌ Erreur dashboard: {e}")


def main():
    """Interface principale du dashboard."""
    st.set_page_config(page_title="CLAUAURENT Paper", layout="wide")
    st.title("🚀 CLAUAURENT – Polymarket Paper Trading (100% Simulation)")

    status = risk.get_status()

    col1, col2, col3 = st.columns(3)
    col1.metric("Capital simulé", f"${status['capital']}")
    col2.metric("Positions ouvertes", status['open_positions'])
    col3.metric("Max Drawdown", f"{status['max_dd']}%")

    st.subheader("Equity Curve")
    st.line_chart(pd.Series(status["equity_curve"]))

    if risk.trades:
        st.subheader("Derniers trades")
        st.dataframe(pd.DataFrame(risk.trades).tail(15))


if __name__ == "__main__":
    main()
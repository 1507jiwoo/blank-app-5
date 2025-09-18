import streamlit as st
import pandas as pd
import plotly.express as px

# 샘플 데이터
df = px.data.gapminder()

st.title("📊 인터랙티브 보고서")

# --- 사이드바 ---
st.sidebar.header("🔧 그래프 선택")
chart_type = st.sidebar.radio(
    "보고서에 표시할 그래프를 선택하세요:",
    ["GDP vs Life Expectancy", "Population by Continent", "GDP Growth Over Time"]
)

# --- 본문 보고서 ---
st.subheader("보고서 시각화")

if chart_type == "GDP vs Life Expectancy":
    fig = px.scatter(
        df.query("year==2007"),
        x="gdpPercap", y="lifeExp",
        size="pop", color="continent",
        hover_name="country", log_x=True
    )
    st.plotly_chart(fig, use_container_width=True)

elif chart_type == "Population by Continent":
    fig = px.bar(
        df.query("year==2007"),
        x="continent", y="pop", color="continent",
        title="2007년 대륙별 인구"
    )
    st.plotly_chart(fig, use_container_width=True)

elif chart_type == "GDP Growth Over Time":

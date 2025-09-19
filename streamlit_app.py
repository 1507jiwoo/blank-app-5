import io
import time
import math
import requests
from datetime import datetime, date, timedelta
from functools import wraps


import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px


# ---------- 설정 ----------
st.set_page_config(page_title="해수면 상승 대시보드 (공개데이터 + 보고서 기반 사용자대시보드)",
                   layout="wide")


TODAY = pd.to_datetime(datetime.now().date())  # 로컬 시스템 날짜 자정 기준 (앱 실행일자)
MAX_DATE = TODAY  # 오늘(로컬 자정) 이후 데이터 제거


# Pretendard 폰트 적용 시도 (있으면 적용)
PRETENDARD_PATH = "/fonts/Pretendard-Bold.ttf"
try:
    with open(PRETENDARD_PATH, "rb"):
        st.markdown(
            f"""
            <style>
            @font-face {{
                font-family: 'PretendardCustom';
                src: url('{PRETENDARD_PATH}');
            }}
            html, body, [class*="css"]  {{
                font-family: PretendardCustom, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans KR", "Apple SD Gothic Neo", "Malgun Gothic", "맑은 고딕", sans-serif;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )
except Exception:
    pass


# ---------- 유틸: 재시도 데코레이터 ----------
def retry(times=3, delay=1.0):
    def deco(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for i in range(times):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    time.sleep(delay)
            raise last_exc
        return wrapper
    return deco


# ---------- 데이터 로드 (공개 데이터) ----------
@st.cache_data(ttl=3600)
def load_global_sea_level():
    urls = [
        "https://datahub.io/core/sea-level-rise/r/sea-level.csv",
        "https://www.climate.gov/sites/default/files/Global_mean_sea_level_1880-2013.csv",
        "https://sealevel.nasa.gov/system/resources/files/2576_SeaLevel_GMSL_1880-2023.csv"
    ]
    last_err = None
    for url in urls:
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            if "Year" in df.columns:
                df = df.rename(columns={"Year":"year"})
                if 'CSIRO_adjusted_GMSL' in df.columns:
                    df['date'] = pd.to_datetime(df['year'].astype(int), format='%Y')
                    df['value'] = df['CSIRO_adjusted_GMSL']
                else:
                    df['date'] = pd.to_datetime(df['year'].astype(int), format='%Y')
                    val_cols = [c for c in df.columns if c.lower().startswith('gmsl') or 'sea' in c.lower() or 'level' in c.lower()]
                    if val_cols:
                        df['value'] = df[val_cols[0]]
                    else:
                        df['value'] = df.iloc[:,1]
            elif 'date' in df.columns or 'Date' in df.columns:
                if 'date' not in df.columns:
                    df = df.rename(columns={c: 'date' for c in df.columns if c.lower()=='date' or c.lower()=='datetime'})
                df['date'] = pd.to_datetime(df['date'])
                val_cols = [c for c in df.columns if c.lower() in ['value','gmsl','sea_level','absolute_sea_level','level']]
                if val_cols:
                    df['value'] = df[val_cols[0]]
                else:
                    df['value'] = df.iloc[:,1]
            else:
                df.columns = ['year','value'] + list(df.columns[2:])
                df['date'] = pd.to_datetime(df['year'].astype(int), format='%Y')
            df = df[['date','value']].dropna().copy()
            df = df[df['date'] <= MAX_DATE]
            df = df.sort_values('date').reset_index(drop=True)
            return df, {"source": url, "fetched": True}
        except Exception as e:
            last_err = e
            continue


    years = np.arange(1880, int(TODAY.year)+1)
    cum = np.cumsum(np.linspace(0.0, 0.0045, len(years))) * 100
    df_example = pd.DataFrame({"date": pd.to_datetime(years, format='%Y'), "value": cum})
    return df_example, {"source": "내장 예시 데이터 (공개 소스 불가)", "fetched": False, "error": str(last_err)}


@st.cache_data(ttl=3600)
def load_korea_coastal_data():
    candidate_urls = [
        "https://data.go.kr/download/15017303/fileData.do",
    ]
    last_err = None
    for url in candidate_urls:
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            if 'date' not in df.columns:
                possible = [c for c in df.columns if 'year' in c.lower() or 'ym' in c.lower() or 'month' in c.lower()]
                if possible:
                    df = df.rename(columns={possible[0]:'date'})
            df['date'] = pd.to_datetime(df['date'])
            val_cols = [c for c in df.columns if 'sea' in c.lower() or '수면' in c or 'm'==c.lower() or 'height' in c.lower()]
            if val_cols:
                df['value'] = df[val_cols[0]]
            else:
                df['value'] = df.iloc[:,1]
            df = df[['date','value']].dropna()
            df = df[df['date'] <= MAX_DATE]
            return df.sort_values('date').reset_index(drop=True), {"source": url, "fetched": True}
        except Exception as e:
            last_err = e
            continue


    years = np.arange(1991, int(TODAY.year)+1)
    values = []
    for y in years:
        if y < 2001:
            inc = 0.00380
        elif y < 2011:
            inc = 0.00013
        else:
            inc = 0.00427
        values.append(inc)
    cum = np.cumsum(values) * 1000
    cum_cm = cum / 10.0
    df_example = pd.DataFrame({"date": pd.to_datetime(years, format='%Y'), "value": cum_cm})
    return df_example, {"source": "(보고서 기반 대한민국 연안 데이터)", "fetched": False, "error": str(last_err)}


# ---------------------- 타이틀 & 뷰 ----------------------
st.title("🌊🏫 내일은 물 위의 학교? : 🚨 해수면 상승의 경고")
st.markdown("**🛶통학길에 카약 타는 날 올지도? : 해수면 SOS**")
st.markdown("**(왼쪽 메뉴)** 공개데이터 대시보드와 보고서 계획표 기반 사용자대시보드를 차례로 제공합니다. 모든 라벨은 한국어입니다.")


with st.spinner("공개 데이터(국제·대한민국) 불러오는 중..."):
    try:
        global_df, global_meta = load_global_sea_level()
    except Exception as e:
        global_df = pd.DataFrame({"date": pd.to_datetime([1900, 1950, 2000]), "value":[0.0, 50.0, 100.0]})
        global_meta = {"source":"내장 예시 - 실패시 대체", "fetched": False, "error": str(e)}
    try:
        korea_df, korea_meta = load_korea_coastal_data()
    except Exception as e:
        korea_df = pd.DataFrame({"date": pd.to_datetime([1991,2000,2010,2020]), "value":[0.0,3.5,6.0,9.1]})
        korea_meta = {"source":"내장 예시 - 실패시 대체", "fetched": False, "error": str(e)}


st.header("공개 데이터 분석 (국제 · 대한민국)")
col1, col2 = st.columns([2,1])


with col1:
    st.subheader("전세계 평균 해수면 변화 (연 단위)")
    st.caption(f"데이터 출처 시도: {global_meta.get('source')}")
    try:
        fig_g = px.line(global_df, x="date", y="value", title="전세계 평균 해수면 변화",
                        labels={"date": "연도", "value": "값(원본 단위)"},
                        template="plotly_white")
        fig_g.update_layout(legend_title_text=None)
        st.plotly_chart(fig_g, use_container_width=True)
    except Exception as e:
        st.error("전세계 데이터 시각화 중 오류가 발생했습니다.")
        st.write(global_df.head())

    # 서론
    st.markdown("""
    최근 관측 자료와 위성 데이터는 전 지구적 해수면 상승과 가속화를 분명히 보여줍니다.  
    우리나라 연안 역시 지난 수십 년 동안 유의미한 상승을 기록하였고(예: 1991~2020 약 9.1cm),  
    이는 청소년의 주거·안전·정신건강에 심각한 영향을 미칠 수 있습니다.
    """)

    # 본론 1-1
    st.markdown("""
    ---
    ## 본론 1 (데이터 분석): 데이터가 말하는 해수면의 비밀
    ### 1-1. 대한민국 해수면 변화 추이와 국제 데이터 분석
    
    최근 기후 변화로 나타나는 폭염 현상은 단순히 대기 문제만이 아니라, 바다의 변화와도 연결되어 있다. 바다는 지구에서 가장 큰 열 저장소로, 온도와 수위가 변하면 지구 전체의 기후 균형이 흔들리게 된다.  
    따라서 해수면의 상승이 실제로 어떤 양상으로 나타나고 있는지 확인하기 위해, 우리는 전 세계와 우리나라의 데이터를 각각 살펴보고 비교 분석하였다.

    첫 번째로, 전 세계 평균 해수면 변화를 살펴보았다. 1880년 이후 지구 평균 해수면은 꾸준히 상승해 왔으며, 특히 1990년대 이후 그 속도가 눈에 띄게 빨라졌다. 이는 빙하가 녹아 바다로 유입되고, 바닷물이 열을 받아 팽창하기 때문으로 해석된다. 결국 바다가 뜨거워지고 있다는 사실을 수치로 확인할 수 있다.  
    (1880년~최근 글로벌 평균 해수면 변화 그래프)

    이어서 1993년부터 2023년까지 위성 고도계로 측정한 호주 주변 해상 해수면 상승률 자료를 보면, 이 지역에서도 뚜렷한 상승세가 나타난다. 특히 남반구 해역은 해양 순환과 기후 패턴의 영향으로 상승 속도가 빠른 편인데, 이는 특정 지역이 다른 곳보다 더 큰 위험에 노출될 수 있다는 사실을 강조한다.
    (1993년부터 2023년까지 위성 고도계를 사용하여 측정한 호주 주변 해상 해수면 상승률(10년당 cm))
    """)

    # 본론 1-2
    st.markdown("""
    두 번째로, 우리나라 연안의 변화를 분석했다. 해양수산부의 관측에 따르면 지난 35년간 대한민국 연안의 평균 해수면은 약 10.7cm 상승하였다. 이는 세계 평균보다 빠른 속도로, 기후 변화의 영향을 우리 사회가 직접적으로 겪고 있음을 보여준다.

    (대한민국 해수면 변화 추이 꺾은선 그래프)

    ### 1-2. 피해 통계와 사례(청소년)
    
    저소득층 어린이·청소년 4명 중 3명은 기후위기로 인한 불안감을 느끼고 있다는 설문조사 결과가 나왔다.  
    환경재단은 지난달 26일부터 지난 4일까지 설문조사를 실시한 결과 저소득층 어린이·청소년 76.3%가 기후위기로 인해 불안감을 느낀다고 답했다고 밝혔다.  
    조사 대상 어린이·청소년의 연령대: 만 5~12세 63.4%/ 만 13~18세 36.6%

    ‘기후위기로 인해 불안감과 무서움을 느낀 적이 있는가?’  
    - ‘매우 그렇다’ 24.8%  
    - ‘그렇다’ 51.5%  
    - ‘불안감을 느끼지 않는다’ 23.7%

    기후재난에 직면한 취약계층 아이들이 겪는 불평등을 조금이나마 해소하고, 미래에 대한 희망을 품을 수 있도록 지원해야함을 알 수 있다.  
    이 세 가지 자료는 해수면 상승이 단순한 자연현상이 아니라 우리들이 만든 기후위기의 결과이며, 그 영향이 우리와 같은 청소년의 생활과 안전, 그리고 마음까지도 위협할 수 있음을 보여준다.  
    따라서 지금 우리가 어떤 대응을 하느냐가 앞으로의 미래를 결정하는 중요한 과제임을 알 수 있다.  
    이제 이러한 데이터를 바탕으로, 해수면 상승이 청소년과 미래 세대에 어떤 영향을 주는지 더 구체적으로 살펴보고, 나아가 정책적 대응의 필요성에 대해서도 탐구해 보겠다.
    """)

    # 본론 2-1
    st.markdown("""
    ---
    ## 본론 2: 해수면 상승의 원인 및 영향 탐구
    ### 2-1. 차오르는 바다와 흔들리는 청소년의 미래

    기온 상승에 따른 해수면 상승은 청소년들의 생활과 건강, 심리적 안정까지 위협받고 있다. 청소년들은 자신들이 마지막 세대가 될 수 있다는 불안과 무력감, 우울증에 시달리고 있으며, 폭염과 전염병 증가로 건강이 악화되고 있다. 농작물 생산 감소로 식량 공급이 줄면서 영양실조에 노출되는 등 다방면에서 피해가 발생하고 있다.  
    이러한 문제의 원인은 지구 온난화에 따른 해수면 상승과 극심한 기후변화에 있으며, 청소년들의 주거환경 불안정, 정신건강 악화, 건강 위협으로 이어진다.
    """)

    # 본론 2-2
    st.markdown("""
    ### 2-2. 정책적 대응의 필요성

    기후변화로 인해 청소년의 정신건강 문제가 심각해짐에 따라 이것을 해결하기 위한 정책적 대응이 필요하다.  
    정부와 교육기관은 청소년이 기후 불안과 우울 등을 조기에 발견하고 상담받을 수 있도록 심리 지원 프로그램을 지원해야 한다.  
    학교에서는 기후변화 교육을 강화해 청소년들이 상황을 올바르게 이해하고 대처할 수 있도록 도와야 한다.  
    지역사회와 의료기관은 협력하여 맞춤형 정신건강 지원 서비스와 치료서비스를 지원하며, 기후 취약계층을 위한 복지 및 안전망도 강화해야 한다.  
    정부는 정신건강과 기후변화 관련 데이터를 체계적으로 수집하고 분석해 실효성 있는 정책을 마련해야 한다.  
    이런 종합적 노력이 청소년이 건강한 미래를 준비하도록 돕고, 사회 전반의 지속 가능성을 높일 수 있다.
    """)

with col2:
    st.subheader("우리나라 연안 해수면 변화(연 단위 요약)")
    st.caption(f"데이터 출처 시도: {korea_meta.get('source')}")
    try:
        fig_k = px.line(korea_df, x="date", y="value", markers=True,
                        title="대한민국 연안 해수면 변화 /관측 기준)",
                        labels={"date":"연도", "value":"해수면 누적 변화 (cm)"}, template="plotly_white")
        st.plotly_chart(fig_k, use_container_width=True)
    except Exception as e:
        st.write(korea_df.head())


    st.markdown("**데이터 다운로드 (대한민국 전처리 표)**")
    csv_k = korea_df.to_csv(index=False).encode('utf-8')
    st.download_button("🔽 대한민국 연안 해수면 데이터 CSV 다운로드", data=csv_k, file_name="korea_sea_level.csv", mime="text/csv")


st.subheader("전세계 해수면 영향 지도 ")
st.markdown("해당 맵은 공개 데이터 중 고해상도 격자 자료에 기반한 정교한 지도를 바로 불러오기 어려운 경우 예시/요약 표현을 사용합니다. 자세한 격자/위성 자료는 NASA / AVISO / Copernicus 원문을 참고하세요.")
map_df = pd.DataFrame({
    "country": ["대한민국","오스트레일리아","미국","몰디브","방글라데시"],
    "lat":[36.5,-25.0,37.1,3.2,23.7],
    "lon":[127.5,133.0,-95.7,73.5,90.4],
    "sea_level_trend_mm_per_year":[3.06,4.0,3.3,6.5,5.0]
})
try:
    fig_map = px.scatter_mapbox(map_df, lat="lat", lon="lon", size="sea_level_trend_mm_per_year",
                                hover_name="country", hover_data=["sea_level_trend_mm_per_year"],
                                title="국가별 해수면 상승률(mm/yr) ",
                                mapbox_style="carto-positron", zoom=1)
    st.plotly_chart(fig_map, use_container_width=True)
except Exception:
    st.write(map_df)


st.markdown("---")


st.header("사용자 입력 기반 대시보드 (보고서 계획표를 코드 내 데이터로 변환하여 시각화)")
st.markdown(" 앱 실행 중 파일 업로드나 추가 입력을 요구하지 않습니다.")


years = np.arange(max(2005, int(TODAY.year)-19), int(TODAY.year)+1)
np.random.seed(42)
temp_anom = np.linspace(0.2, 1.0, len(years)) + np.random.normal(0, 0.05, len(years))
sea_cm = np.cumsum( (temp_anom - temp_anom.mean())*0.8 + 0.3 )
user_timeseries = pd.DataFrame({"date": pd.to_datetime(years, format='%Y'), "기온이상(℃)": temp_anom, "해수면_누적(cm)": sea_cm})


survey = pd.DataFrame({
    "항목":["기후위기 불안(매우 그렇다)","기후위기 불안(그렇다)","불안감 없음"],
    "비율":[24.8,51.5,23.7]
})
age_dist = pd.DataFrame({"연령대":["만 5~12세","만 13~18세"], "비율":[63.4,36.6]})


jobs = pd.DataFrame({
    "영향인식":["높음","보통","낮음"],
    "비율":[55,30,15]
})


st.subheader("1) 지난 20년간 기온과 해수면 ")
st.caption("데이터: 보고서 계획표 기반 합성 데이터 (앱 내 생성)")
with st.sidebar.expander("시계열 옵션 (사용자 입력 대시보드)"):
    smoothing = st.checkbox("이동평균 스무딩 적용 (3년)", value=True)
    show_temp = st.checkbox("기온 이상 표시", value=True)
    show_sea = st.checkbox("해수면 표시", value=True)


ts = user_timeseries.copy()
if smoothing:
    ts["기온이상(℃)_스무딩"] = ts["기온이상(℃)"].rolling(3, center=True, min_periods=1).mean()
    ts["해수면_누적(cm)_스무딩"] = ts["해수면_누적(cm)"].rolling(3, center=True, min_periods=1).mean()


fig_ts = px.line()
if show_temp:
    ytemp = "기온이상(℃)_스무딩" if smoothing else "기온이상(℃)"
    fig_ts.add_scatter(x=ts['date'], y=ts[ytemp], mode='lines+markers', name='기온 이상 (℃)')
if show_sea:
    ysea = "해수면_누적(cm)_스무딩" if smoothing else "해수면_누적(cm)"
    fig_ts.add_scatter(x=ts['date'], y=ts[ysea], mode='lines+markers', name='해수면 누적 (cm)', yaxis="y2")


fig_ts.update_layout(
    title="(보고서 기반) 지난 20년 기온 이상 vs 해수면 누적 변화 ",
    xaxis_title="연도",
    yaxis=dict(title="기온 이상 (℃)"),
    yaxis2=dict(title="해수면 누적 (cm)", overlaying="y", side="right"),
    legend_title_text=None,
    template="plotly_white"
)
st.plotly_chart(fig_ts, use_container_width=True)


st.download_button("🔽 시계열(보고서 기반) CSV 다운로드", data=ts.to_csv(index=False).encode('utf-8'), file_name="user_timeseries_report.csv", mime="text/csv")


st.markdown("---")
st.subheader("2) 청소년 대상 기후불안 설문 요약")
col_a, col_b = st.columns(2)
with col_a:
    st.markdown("### 설문: 불안감 응답 비율")
    fig_pie = px.pie(survey, names='항목', values='비율', title="기후위기로 인한 불안감 응답 비율 ")
    st.plotly_chart(fig_pie, use_container_width=True)
with col_b:
    st.markdown("### 설문: 연령대 분포")
    fig_age = px.bar(age_dist, x='연령대', y='비율', title="조사 대상 연령대 분포 ", labels={"연령대":"연령대","비율":"비율(%)"})
    st.plotly_chart(fig_age, use_container_width=True)


st.markdown("설문 데이터 다운로드")
st.download_button("🔽 설문 데이터 CSV 다운로드", data=survey.to_csv(index=False).encode('utf-8'), file_name="survey_summary.csv", mime="text/csv")


st.markdown("---")
st.subheader("3) 청소년 미래 직업에 대한 기후위기 인식 ")
st.caption("보고서 텍스트에서 도출한 핵심 메시지 시각화 (합성 데이터)")
fig_jobs = px.bar(jobs, x='영향인식', y='비율', labels={'영향인식':'인식','비율':'비율(%)'}, title="청소년의 기후위기 영향 인식 (예시)")
st.plotly_chart(fig_jobs, use_container_width=True)
st.download_button("🔽 직업·인식 데이터 CSV 다운로드", data=jobs.to_csv(index=False).encode('utf-8'), file_name="youth_jobs_opinion.csv", mime="text/csv")


st.markdown("---")


# 하단: 원본 데이터/자료 링크 표시 (사용자가 원문 확인 가능하도록)
st.markdown("### 참고자료")
st.markdown("""
- NOAA / Climate.gov — Global mean sea level 자료: [https://www.climate.gov/maps-data/dataset/global-mean-sea-level-graph](https://www.climate.gov/maps-data/dataset/global-mean-sea-level-graph)  
- NASA Sea Level / PO.DAAC / JPL — 해수면 변화 분석: [https://sealevel.nasa.gov/](https://sealevel.nasa.gov/)  
- CSIRO / Bureau of Meteorology (호주 해역/위성 관측): [https://www.csiro.au/](https://www.csiro.au/) , [https://www.bom.gov.au/](https://www.bom.gov.au/)  
- AVISO / Copernicus 해수면 지표: [https://www.aviso.altimetry.fr/](https://www.aviso.altimetry.fr/) , [https://climate.copernicus.eu/](https://climate.copernicus.eu/)  
- 대한민국(해양수산부 / 국립해양조사원) 연안 해수면 통계 및 공공데이터: [https://coast.mof.go.kr/](https://coast.mof.go.kr/) , [https://www.data.go.kr/](https://www.data.go.kr/)
""")

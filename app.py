"""2028 대입개편 대비 서울대 목표 연도별 커리큘럼 플래너.

실행: streamlit run app.py
"""

import json
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

import ai_coach
import curriculum as cur

# --- 색상·표기 체계 (타임라인·차트·뱃지가 같은 값을 쓴다) --------------------

STAGE_COLORS = {"초등": "#7FB3D5", "중등": "#F5B041", "고등": "#CD6155"}

SUBJECT_COLORS = {
    "국어": "#5B8FF9",
    "수학": "#5AD8A6",
    "영어": "#F6BD16",
    "탐구": "#E8684A",
    "비교과/진로": "#9270CA",
}

MILESTONE_ICONS = {"학습": "📘", "진로": "🧭", "시험": "📝", "서류": "📄"}

PLOTLY_TEMPLATE = "plotly_white"
CHART_MARGIN = dict(l=10, r=10, t=50, b=10)

ERROR_MESSAGES = {
    "no_key": ".env에 OPENAI_API_KEY가 없습니다. 규칙 기반 커리큘럼만 표시합니다.",
    "auth": "OpenAI API 키가 올바르지 않습니다. .env의 OPENAI_API_KEY를 확인해주세요.",
    "rate_limit": "OpenAI API 호출 한도를 초과했습니다. 잠시 후 다시 시도해주세요.",
    "network": "OpenAI 서버에 연결하지 못했습니다. 네트워크 상태를 확인해주세요.",
    "parse": "AI 응답을 해석하지 못했습니다. 규칙 기반 커리큘럼을 그대로 사용합니다.",
    "api": "OpenAI API가 오류를 반환했습니다. 잠시 후 다시 시도해주세요.",
    "import": "openai 패키지를 불러오지 못했습니다. pip install -r requirements.txt를 실행해주세요.",
    "unknown": "AI 호출 중 알 수 없는 오류가 발생했습니다. 규칙 기반 커리큘럼은 그대로 사용할 수 있습니다.",
}


def badge(text: str, color: str) -> str:
    return (
        f"<span style='background:{color};color:#fff;padding:2px 10px;"
        f"border-radius:12px;font-size:0.8rem;white-space:nowrap;'>{text}</span>"
    )


# --- 데이터 로드 -----------------------------------------------------------


@st.cache_data(show_spinner=False)
def _load_policy(_mtime: float) -> tuple[dict | None, str | None]:
    try:
        return cur.load_policy(), None
    except cur.PolicyLoadError as exc:
        return None, str(exc)


def load_policy_cached() -> tuple[dict | None, str | None]:
    """제도 데이터를 읽는다. 파일이 바뀌면 캐시가 자동으로 갱신된다.

    실패해도 앱은 계속 동작해야 한다.
    """
    try:
        mtime = cur.POLICY_PATH.stat().st_mtime
    except OSError:
        mtime = 0.0
    return _load_policy(mtime)


# --- 입력 ------------------------------------------------------------------


def render_sidebar() -> dict:
    st.sidebar.title("🎓 학생 정보")

    grade = st.sidebar.selectbox(
        "현재 학년",
        cur.SELECTABLE_GRADES,  # 초1~고1, 10개만 선택 가능
        index=cur.SELECTABLE_GRADES.index("중1"),
        help="고2·고3은 선택할 수 없습니다. 계획에는 자동으로 포함됩니다.",
    )
    track = st.sidebar.selectbox("목표 계열", cur.TRACKS, index=0)
    major = st.sidebar.text_input(
        "관심 분야·희망 전공", placeholder="예: 컴퓨터공학, 경제학", help="비워 두어도 됩니다."
    )

    st.sidebar.markdown("**과목별 상황**")
    strengths = st.sidebar.multiselect("강점 과목", cur.INPUT_SUBJECTS)
    weaknesses = st.sidebar.multiselect("약점 과목", cur.INPUT_SUBJECTS)
    weekly_hours = st.sidebar.slider(
        "주당 학습 가능 시간", 5, 40, 15, help="학교 수업 외에 스스로 학습할 수 있는 시간"
    )

    overlap = sorted(set(strengths) & set(weaknesses))
    if overlap:
        st.sidebar.warning(
            f"{', '.join(overlap)} 과목이 강점과 약점에 모두 선택되어 비중 보정에서 상쇄됩니다."
        )

    return {
        "grade": grade,
        "track": track,
        "major": major,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "weekly_hours": weekly_hours,
    }


def profile_signature(profile: dict, base_year: int) -> str:
    """입력이 바뀌면 캐시된 AI 결과를 버리기 위한 서명.

    주당 학습 시간은 커리큘럼 내용을 바꾸지 않고 시간 배분 계산에만 쓰이므로
    서명에 넣지 않는다. 슬라이더를 움직였다고 AI 결과를 버릴 이유는 없다.
    """
    return json.dumps(
        {
            "grade": profile["grade"],
            "track": profile["track"],
            "major": ai_coach.sanitize_text(profile["major"]),
            "strengths": sorted(profile["strengths"]),
            "weaknesses": sorted(profile["weaknesses"]),
            "base_year": base_year,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


# --- 상단 KPI --------------------------------------------------------------


def months_until_suneung(admission_year: int, today: date | None = None) -> int:
    """수능(대입 학년도 전년 11월)까지 남은 개월 수."""
    today = today or date.today()
    target_year, target_month = admission_year - 1, 11
    return max((target_year - today.year) * 12 + (target_month - today.month), 0)


def render_kpis(profile: dict, base_year: int, admission_year: int, plan_count: int) -> None:
    months = months_until_suneung(admission_year)
    cards = [
        ("대입 학년도", f"{admission_year}학년도", f"{base_year}학년도 기준"),
        ("수능까지", f"{months // 12}년 {months % 12}개월", f"{admission_year - 1}년 11월 예정"),
        ("계획 연도 수", f"{plan_count}년", f"{profile['grade']} → 고3"),
        ("적용 제도", "2028 개편", "통합형 수능 · 내신 5등급"),
    ]
    for col, (label, value, note) in zip(st.columns(4), cards):
        col.metric(label, value)
        col.caption(note)


# --- 시각화 ----------------------------------------------------------------


def render_timeline(plans: list[dict]) -> None:
    df = pd.DataFrame(
        [
            {
                "학년": f"{p['year']} {p['school_year']}",
                "시작": f"{p['year']}-03-01",
                "종료": f"{p['year'] + 1}-03-01",
                "학교급": p["stage"],
                "핵심 목표": p["headline"],
            }
            for p in plans
        ]
    )
    fig = px.timeline(
        df,
        x_start="시작",
        x_end="종료",
        y="학년",
        color="학교급",
        color_discrete_map=STAGE_COLORS,
        hover_data={"핵심 목표": True, "시작": False, "종료": False},
        category_orders={"학년": list(df["학년"]), "학교급": ["초등", "중등", "고등"]},
        template=PLOTLY_TEMPLATE,
    )
    fig.update_yaxes(autorange="reversed", title="")
    fig.update_xaxes(dtick="M12", tickformat="%Y년")  # 연도가 적어도 월 단위 눈금이 나오지 않게
    fig.update_layout(
        title="연도별 로드맵",
        xaxis_title="학년도 (3월 ~ 다음해 2월)",
        legend_title="학교급",
        height=110 + 40 * len(df),
        margin=CHART_MARGIN,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_weight_trend(plans: list[dict]) -> None:
    rows = [
        {"연도": p["year"], "영역": subject, "비중(%)": p["subjects"][subject]["weight"]}
        for p in plans
        for subject in cur.SUBJECTS
    ]
    fig = px.area(
        pd.DataFrame(rows),
        x="연도",
        y="비중(%)",
        color="영역",
        color_discrete_map=SUBJECT_COLORS,
        category_orders={"영역": cur.SUBJECTS},
        template=PLOTLY_TEMPLATE,
    )
    fig.update_xaxes(dtick=1, title="학년도")
    fig.update_yaxes(title="비중 (%)", range=[0, 100])
    fig.update_layout(
        title="영역별 학습 비중 변화", legend_title="영역", height=380, margin=CHART_MARGIN
    )
    st.plotly_chart(fig, use_container_width=True)


def render_weekly_hours(plan: dict, weekly_hours: int) -> None:
    rows = [
        {
            "영역": subject,
            "시간": round(plan["subjects"][subject]["weight"] * weekly_hours / 100, 1),
        }
        for subject in cur.SUBJECTS
    ]
    fig = px.bar(
        pd.DataFrame(rows),
        x="영역",
        y="시간",
        color="영역",
        color_discrete_map=SUBJECT_COLORS,
        category_orders={"영역": cur.SUBJECTS},
        text="시간",
        template=PLOTLY_TEMPLATE,
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_yaxes(title="시간 / 주")
    fig.update_xaxes(title="")
    fig.update_layout(
        title=f"{plan['year']}년 주간 학습시간 배분 (총 {weekly_hours}시간)",
        showlegend=False,
        height=380,
        margin=CHART_MARGIN,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_year_detail(plan: dict) -> None:
    with st.container(border=True):
        head, tags = st.columns([3, 1])
        head.markdown(f"#### {plan['year']}년 · {plan['school_year']}")
        tags_html = badge(plan["stage"], STAGE_COLORS[plan["stage"]])
        if plan["band"] != plan["stage"]:
            tags_html += " " + badge(plan["band"], "#5D6D7E")
        tags.markdown(tags_html, unsafe_allow_html=True)
        st.markdown(f"**{plan['headline']}**")
        st.divider()

        left, right = st.columns([1, 1])
        with left:
            st.markdown("**🎯 이 해의 목표**")
            for goal in plan["goals"]:
                st.markdown(f"- {goal}")
            st.markdown("**🏛 서울대 연결 포인트**")
            st.markdown(f"- {plan['snu_link']}")
        with right:
            st.markdown("**📚 영역별 실행 항목**")
            for subject in cur.SUBJECTS:
                info = plan["subjects"][subject]
                actions = " / ".join(info["actions"]) or "-"
                st.markdown(f"- **{subject}** `{info['weight']}%` — {actions}")

        if plan.get("policy_notes") or plan.get("risks"):
            st.divider()
            note_col, risk_col = st.columns(2)
            with note_col:
                if plan.get("policy_notes"):
                    st.markdown("**📌 적용되는 2028 개편 사항**")
                    for note in plan["policy_notes"]:
                        st.markdown(f"- {note}")
            with risk_col:
                if plan.get("risks"):
                    st.markdown("**⚠️ 이 시기에 흔한 실수**")
                    for risk in plan["risks"]:
                        st.markdown(f"- {risk}")


def render_milestones(plans: list[dict]) -> None:
    rows = cur.milestone_rows(plans)
    for row in rows:
        row["구분"] = f"{MILESTONE_ICONS.get(row['구분'], '•')} {row['구분']}"
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True,
        height=min(len(rows) * 35 + 38, 640),
        column_config={
            "연도": st.column_config.NumberColumn("연도", format="%d", width="small"),
            "학년": st.column_config.TextColumn("학년", width="small"),
            "분기": st.column_config.TextColumn("분기", width="small"),
            "구분": st.column_config.TextColumn("구분", width="small"),
            "내용": st.column_config.TextColumn("내용", width="large"),
        },
    )


def render_ai_card(
    ai_result: dict | None,
    weight_changes: list[tuple[str, int, int]],
    weekly_hours: int,
) -> None:
    with st.container(border=True):
        st.markdown("#### 🤖 AI 커리큘럼 코칭")

        if weight_changes:
            changes = " · ".join(f"{s} {b}% → {a}%" for s, b, a in weight_changes)
            st.caption(f"강점·약점 입력에 따른 비중 보정: {changes}")

        if not ai_result:
            st.info(
                "왼쪽 사이드바의 **AI 커리큘럼 생성하기** 버튼을 누르면 "
                "학생 맞춤 실행 계획과 코칭을 받아옵니다. "
                "누르지 않아도 위의 커리큘럼은 그대로 사용할 수 있습니다."
            )
            return

        coaching = ai_result.get("coaching") or {}
        if coaching.get("summary"):
            st.markdown(coaching["summary"])
        if coaching.get("weight_reason"):
            st.markdown(f"**학습 비중 배분** — {coaching['weight_reason']}")
        if coaching.get("cautions"):
            st.markdown("**놓치기 쉬운 점**")
            for caution in coaching["cautions"]:
                st.markdown(f"- {caution}")

        generated_hours = ai_result.get("weekly_hours")
        if generated_hours is not None and generated_hours != weekly_hours:
            st.caption(
                f"이 코칭은 주당 {generated_hours}시간 기준으로 생성되었습니다. "
                f"현재 설정({weekly_hours}시간)에 맞추려면 다시 생성해 주세요."
            )


def render_downloads(plans: list[dict], grade: str) -> None:
    rows = cur.plans_to_rows(plans)
    csv = pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig")
    payload = json.dumps(plans, ensure_ascii=False, indent=2).encode("utf-8")

    col1, col2 = st.columns(2)
    col1.download_button(
        "⬇️ CSV 다운로드",
        csv,
        file_name=f"curriculum_{grade}.csv",
        mime="text/csv",
        use_container_width=True,
    )
    col2.download_button(
        "⬇️ JSON 다운로드",
        payload,
        file_name=f"curriculum_{grade}.json",
        mime="application/json",
        use_container_width=True,
    )


def render_guide() -> None:
    # expanded 값이 실행마다 바뀌면 사용자가 접어도 다시 펼쳐진다. 첫 진입 상태로 고정한다.
    with st.expander("처음이신가요? 사용법 보기", expanded=True):
        st.markdown(
            """
1. **왼쪽 사이드바에서 현재 학년을 선택**하세요. (초1 ~ 고1)
2. 목표 계열·희망 전공·강점과 약점 과목·주당 학습 가능 시간을 입력하면 학습 비중이 조정됩니다.
3. 화면에 **현재 학년부터 고3까지의 연도별 로드맵**이 바로 그려집니다.
4. **AI 커리큘럼 생성하기** 버튼을 누르면 학생 맞춤 실행 계획으로 내용이 바뀝니다.
5. 아래에서 커리큘럼을 CSV/JSON으로 내려받을 수 있습니다.

> 예시: **중2** 학생을 선택하면 2031학년도 대입까지 5년치 계획이 만들어지고,
> 고1 구간에는 내신 5등급제와 고교학점제 과목 설계가 자동으로 포함됩니다.
            """
        )


# --- AI 호출 ---------------------------------------------------------------


def run_ai(plans: list[dict], profile: dict, policy: dict | None, admission_year: int) -> None:
    """버튼을 눌렀을 때만 호출한다. 결과는 session_state에 저장한다."""
    payload = dict(profile, admission_year=admission_year)
    with st.spinner(f"커리큘럼을 설계하는 중입니다... ({len(plans)}년치, 최대 1분 정도 걸립니다)"):
        try:
            result = ai_coach.generate_curriculum(plans, payload, policy)
        except ai_coach.AICoachError as exc:
            # 이전에 성공한 결과가 있으면 그대로 둔다. 실패했다고 버릴 이유가 없다.
            st.error(ERROR_MESSAGES.get(exc.kind, f"AI 호출 중 오류가 발생했습니다: {exc}"))
            return
        result["weekly_hours"] = profile["weekly_hours"]
        st.session_state.ai_result = result


# --- 메인 ------------------------------------------------------------------


def main() -> None:
    st.set_page_config(
        page_title="2028 대입 커리큘럼 플래너", page_icon="🎓", layout="wide"
    )

    st.title("🎓 2028 대입개편 대비 커리큘럼 플래너")
    st.caption("서울대 진학을 목표로, 현재 학년부터 고3까지의 연도별 학습 로드맵을 설계합니다.")

    policy, policy_error = load_policy_cached()
    if policy_error:
        st.warning(f"{policy_error} 제도 관련 안내 없이 커리큘럼만 표시합니다.")

    profile = render_sidebar()
    base_year = cur.get_base_school_year()
    admission_year = cur.calc_admission_year(profile["grade"], base_year)

    # 입력이 바뀌면 이전 학년의 AI 결과가 남지 않도록 초기화한다.
    signature = profile_signature(profile, base_year)
    if st.session_state.get("ai_signature") != signature:
        st.session_state.ai_signature = signature
        if st.session_state.get("ai_result"):
            st.session_state.ai_result = None
            st.info("입력이 바뀌어 이전 AI 결과를 초기화했습니다. 다시 생성해 주세요.")

    base_plans = cur.build_skeleton(profile["grade"], base_year, policy)
    plans = cur.adjust_weights(base_plans, profile["strengths"], profile["weaknesses"])
    weight_changes = cur.weight_change_summary(base_plans, plans)

    st.sidebar.divider()
    has_key = ai_coach.has_api_key()
    if st.sidebar.button(
        "🤖 AI 커리큘럼 생성하기",
        type="primary",
        use_container_width=True,
        disabled=not has_key,
        help=None if has_key else ".env에 OPENAI_API_KEY를 넣어야 사용할 수 있습니다.",
    ):
        run_ai(plans, profile, policy, admission_year)
    if not has_key:
        st.sidebar.caption("`.env`에 OPENAI_API_KEY가 없어 AI 생성은 사용할 수 없습니다.")

    ai_result = st.session_state.get("ai_result")
    plans = ai_coach.merge_ai_into_plans(plans, ai_result)

    # 상세 연도 선택값을 먼저 확정해야 주간 학습시간 차트에서 함께 쓸 수 있다.
    years = [p["year"] for p in plans]
    if st.session_state.get("detail_year") not in years:
        st.session_state.detail_year = years[0]
    selected_plan = next(p for p in plans if p["year"] == st.session_state.detail_year)

    render_guide()
    render_kpis(profile, base_year, admission_year, len(plans))

    st.divider()
    render_timeline(plans)

    left, right = st.columns(2)
    with left:
        render_weight_trend(plans)
    with right:
        render_weekly_hours(selected_plan, profile["weekly_hours"])

    st.divider()
    st.subheader("연도별 상세")
    st.selectbox(
        "연도 선택",
        years,
        key="detail_year",
        format_func=lambda y: f"{y}년 ({next(p['school_year'] for p in plans if p['year'] == y)})",
        help="선택한 연도가 위의 주간 학습시간 배분에도 반영됩니다.",
    )
    render_year_detail(selected_plan)

    st.divider()
    st.subheader("마일스톤")
    st.caption("분기별 체크포인트입니다. " + " · ".join(f"{v} {k}" for k, v in MILESTONE_ICONS.items()))
    render_milestones(plans)

    st.divider()
    render_ai_card(ai_result, weight_changes, profile["weekly_hours"])

    st.divider()
    st.subheader("내려받기")
    render_downloads(plans, profile["grade"])

    st.divider()
    st.caption(
        "본 커리큘럼은 참고용이며, 최종 전형 요강은 교육부·서울대 입학본부 공식 발표를 확인해야 합니다."
    )
    meta = [f"제도 데이터 기준 시점: {policy.get('as_of', '미상')}"] if policy else []
    meta.append(f"AI 모델: {ai_coach.get_model_name()}")
    st.caption(" · ".join(meta))


if __name__ == "__main__":
    main()

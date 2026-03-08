# -*- coding: utf-8 -*-
"""卡住了？ — AI 决策助手 + 决策日志"""
import streamlit as st

st.set_page_config(page_title="Stuck?", page_icon="🚦", layout="wide")

from auth import require_auth
require_auth()

from engine import (
    all_keys_ready, run_decision_engine,
    save_decision_log, load_decision_logs, export_decision_csv,
    load_escalation_rules, save_escalation_rules,
    list_skills, build_skill_context,
)
from i18n import t, output_lang_instruction

lang = st.session_state.get("lang", "zh")

if not all_keys_ready():
    st.warning(t("need_config", lang))
    st.stop()

st.title(t("dk_title", lang))
st.caption(t("dk_desc", lang))
st.info(t("dk_warm", lang))

tab_new, tab_history, tab_rules = st.tabs([
    t("dk_tab_new", lang),
    t("dk_tab_history", lang),
    t("dk_tab_rules", lang),
])

# ━━ Tab 1: 新决策 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_new:
    with st.form("decision_form"):
        situation = st.text_area(
            t("dk_situation", lang),
            placeholder=t("dk_situation_ph", lang),
            height=100,
        )
        col1, col2 = st.columns(2)
        with col1:
            owner = st.text_input(t("dk_owner", lang))
        with col2:
            skills = list_skills()
            skill_options = {s["file"]: s["title"] for s in skills}
            selected_skills = st.multiselect(
                t("skill_label", lang),
                options=list(skill_options.keys()),
                format_func=lambda x: skill_options.get(x, x),
                max_selections=3,
            ) if skills else []

        options_text = st.text_area(
            t("dk_options", lang),
            placeholder=t("dk_options_ph", lang),
            height=80,
        )
        submitted = st.form_submit_button(
            t("dk_start", lang), type="primary", use_container_width=True,
        )

    if submitted and situation.strip():
        skill_ctx = build_skill_context(selected_skills) if selected_skills else ""
        lang_instr = output_lang_instruction(lang)
        with st.status(t("dk_running", lang), expanded=True) as status:
            progress = st.empty()
            try:
                result = run_decision_engine(
                    situation=situation.strip() + lang_instr,
                    owner=owner.strip(),
                    options_text=options_text.strip(),
                    skill_context=skill_ctx,
                    progress_container=progress,
                )
                status.update(label=t("dk_done", lang), state="complete", expanded=False)
            except Exception as e:
                status.update(label=t("error", lang), state="error")
                st.error(f"{t('error', lang)}{e}")
                st.stop()
        st.session_state["decision_result"] = result

    result = st.session_state.get("decision_result")
    if result:
        cls = result["classification"]
        log = result["log_entry"]

        st.divider()

        level_raw = cls.get("level", "")
        if "必须" in level_raw or "Must" in level_raw:
            level_display = t("dk_level_1", lang)
            level_color = "red"
        elif "先试" in level_raw or "Try" in level_raw:
            level_display = t("dk_level_2", lang)
            level_color = "orange"
        else:
            level_display = t("dk_level_3", lang)
            level_color = "green"

        col_level, col_rule = st.columns([1, 2])
        with col_level:
            st.markdown(f"### {t('dk_level', lang)}")
            st.markdown(
                f"<div style='font-size:1.4rem; font-weight:700; color:{level_color}; "
                f"padding:0.5rem 0'>{level_display}</div>",
                unsafe_allow_html=True,
            )
        with col_rule:
            st.markdown(f"**{t('dk_matched', lang)}：** {cls.get('matched_rule', '—')}")
            st.markdown(f"**{t('dk_reason', lang)}：** {cls.get('reason', '—')}")

        if "必须" in level_raw or "Must" in level_raw:
            st.success(t("dk_warm_level1", lang))
        elif "先试" in level_raw or "Try" in level_raw:
            st.info(t("dk_warm_level2", lang))
        else:
            st.success(t("dk_warm_level3", lang))

        st.markdown(f"**{t('dk_suggestion', lang)}：**")
        st.info(cls.get("suggestion", "—"))

        st.divider()
        st.subheader(t("dk_log_preview", lang))
        st.caption(t("dk_edit_hint", lang))

        ec1, ec2 = st.columns(2)
        with ec1:
            log_date = st.text_input(
                "日期" if lang == "zh" else "Date",
                value=log.get("date", ""), key="log_date")
            log_owner = st.text_input(
                "负责人" if lang == "zh" else "Owner",
                value=log.get("owner", owner), key="log_owner")
            log_problem = st.text_input(
                "情境" if lang == "zh" else "Situation",
                value=log.get("problem", ""), key="log_problem")
            log_options = st.text_input(
                "可选方案" if lang == "zh" else "Options",
                value=log.get("options", ""), key="log_options")
        with ec2:
            log_decision = st.text_input(
                "决定" if lang == "zh" else "Decision",
                value=log.get("decision", ""), key="log_decision")
            budget_opts = ["预算内", ">10000", "超预算"]
            budget_en = {"预算内": "Within budget", ">10000": ">10000 RMB", "超预算": "Over budget"}
            log_budget = st.selectbox(
                "预算影响" if lang == "zh" else "Budget Impact",
                budget_opts,
                index=budget_opts.index(log.get("budget_impact", "预算内")) if log.get("budget_impact") in budget_opts else 0,
                format_func=lambda x: budget_en.get(x, x) if lang == "en" else x,
                key="log_budget")
            risk_opts = ["低", "中", "高"]
            risk_en = {"低": "Low", "中": "Medium", "高": "High"}
            log_risk = st.selectbox(
                "风险等级" if lang == "zh" else "Risk Level",
                risk_opts,
                index=risk_opts.index(log.get("risk_level", "低")) if log.get("risk_level") in risk_opts else 0,
                format_func=lambda x: risk_en.get(x, x) if lang == "en" else x,
                key="log_risk")
            log_reason = st.text_input(
                "原因（一句话）" if lang == "zh" else "Reason (one line)",
                value=log.get("reason", ""), key="log_reason")

        if st.button(t("dk_save", lang), type="primary", use_container_width=True):
            final_entry = {
                "date": log_date,
                "owner": log_owner,
                "problem": log_problem,
                "options": log_options,
                "decision": log_decision,
                "budget_impact": log_budget,
                "risk_level": log_risk,
                "reason": log_reason,
                "level": level_raw,
            }
            try:
                save_decision_log(final_entry)
                st.success(t("dk_saved", lang))
                st.session_state["decision_result"] = None
                st.rerun()
            except Exception as e:
                st.error(f"{t('save_fail', lang)}{e}")


# ━━ Tab 2: 历史记录 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_history:
    logs = load_decision_logs()
    if not logs:
        st.info(t("dk_no_history", lang))
    else:
        search = st.text_input(
            "🔍", placeholder="Search..." if lang == "en" else "搜索…",
            label_visibility="collapsed",
        )
        filtered = logs
        if search.strip():
            q = search.strip().lower()
            filtered = [
                l for l in logs
                if q in str(l.get("problem", "")).lower()
                or q in str(l.get("owner", "")).lower()
                or q in str(l.get("decision", "")).lower()
                or q in str(l.get("level", "")).lower()
            ]

        for i, log in enumerate(filtered):
            level_raw = log.get("level", "")
            if "必须" in level_raw:
                badge = "🔴"
            elif "先试" in level_raw:
                badge = "🟡"
            else:
                badge = "🟢"

            label = f"{badge} {log.get('date', '—')} | {log.get('owner', '—')} | {log.get('problem', '—')[:40]}"
            with st.expander(label):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**情境：** {log.get('problem', '—')}")
                    st.markdown(f"**可选方案：** {log.get('options', '—')}")
                    st.markdown(f"**决定：** {log.get('decision', '—')}")
                with c2:
                    st.markdown(f"**预算影响：** {log.get('budget_impact', '—')}")
                    st.markdown(f"**风险等级：** {log.get('risk_level', '—')}")
                    st.markdown(f"**原因：** {log.get('reason', '—')}")
                    st.markdown(f"**级别：** {level_raw}")

        if filtered:
            csv_data = export_decision_csv(filtered)
            st.download_button(
                t("dk_export_csv", lang),
                data=csv_data,
                file_name="decision_logs.csv",
                mime="text/csv",
                use_container_width=True,
            )


# ━━ Tab 3: 升级规则 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_rules:
    rules_content = load_escalation_rules()
    st.markdown(rules_content)

    with st.expander(t("dk_rules_edit", lang)):
        edited = st.text_area(
            "Markdown",
            value=rules_content,
            height=400,
            label_visibility="collapsed",
        )
        if st.button(t("dk_rules_save", lang), type="primary"):
            try:
                save_escalation_rules(edited)
                st.success(t("dk_rules_saved", lang))
                st.rerun()
            except Exception as e:
                st.error(f"{t('save_fail', lang)}{e}")

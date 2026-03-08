# -*- coding: utf-8 -*-
"""简单密码保护 — 云端部署时通过 STUDIO_PASSWORD 环境变量启用"""
import os
import streamlit as st


def require_auth():
    """检查是否已通过密码验证。未验证时显示登录页并 st.stop()。"""
    pwd = os.environ.get("STUDIO_PASSWORD", "")
    if not pwd:
        return
    if st.session_state.get("authenticated"):
        return
    st.markdown("## ⚡ AI Creative Studio")
    st.text_input("请输入访问密码", type="password", key="_page_pwd")
    if st.button("进入", type="primary"):
        if st.session_state._page_pwd == pwd:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("密码错误")
    st.stop()

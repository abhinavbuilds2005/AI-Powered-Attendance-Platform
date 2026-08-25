import streamlit as st

def subject_card(name, code, section, stats=None, footer_callback=None):
    stats_html = ""
    if stats:
        stats_html = '<div style="display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px;">'
        for icon, label, value in stats:
            stats_html += f"""
            <div style="background: #F1F5F9; border: 1px solid #E2E8F0; padding: 6px 14px; border-radius: 12px; font-size: 0.88rem; color: #334155; display: inline-flex; align-items: center; gap: 6px;">
                <span>{icon}</span>
                <span style="color: #64748B; font-size: 0.8rem;">{label}:</span>
                <strong style="color: #0F172A; font-weight: 700;">{value}</strong>
            </div>
            """
        stats_html += "</div>"

    card_html = f"""
    <div style="background: white; border-radius: 1.25rem; border: 1px solid #E2E8F0; box-shadow: 0 4px 12px -2px rgba(0, 0, 0, 0.05); padding: 1.5rem; margin-bottom: 1.25rem; border-left: 6px solid #4F46E5; transition: transform 0.2s ease, box-shadow 0.2s ease;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 10px;">
            <div>
                <h3 style="margin: 0; color: #0F172A; font-size: 1.25rem; font-weight: 700;">{name}</h3>
                <div style="margin-top: 6px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                    <span style="background: #EEF2FF; color: #4F46E5; padding: 3px 10px; border-radius: 8px; font-weight: 700; font-size: 0.8rem; border: 1px solid #C7D2FE;">
                        {code}
                    </span>
                    <span style="color: #64748B; font-size: 0.85rem;">Section: <strong>{section}</strong></span>
                </div>
            </div>
        </div>
        {stats_html}
    </div>
    """

    st.markdown(card_html, unsafe_allow_html=True)

    if footer_callback:
        footer_callback()

import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import extra_streamlit_components as stx

# --- 1. הגדרות עמוד ועיצוב CSS מתקדם (UI/UX) ---
st.set_page_config(page_title="SodaClub Premium", layout="centered", page_icon="🥤")

# הזרקת עיצוב מותאם אישית
st.markdown("""
    <style>
    /* הגדרות כלליות ו-RTL */
    .stApp { direction: rtl; text-align: right; background-color: #f8f9fa; }
    
    /* עיצוב כרטיסי ה-Metric */
    div[data-testid="stMetric"] {
        background-color: white;
        padding: 15px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        border: 1px solid #e9ecef;
    }
    
    /* עיצוב כפתור הקנייה הראשי */
    .main-button button {
        background: linear-gradient(135deg, #1E88E5 0%, #1565C0 100%);
        color: white !important;
        border: none;
        padding: 20px;
        font-size: 20px !important;
        height: auto !important;
        border-radius: 15px !important;
        box-shadow: 0 4px 15px rgba(21, 101, 192, 0.3);
        transition: all 0.3s ease;
    }
    .main-button button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(21, 101, 192, 0.4);
    }
    
    /* עיצוב טאבים */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: white;
        border-radius: 8px 8px 0 0;
        padding: 10px 20px;
        border: 1px solid #e9ecef;
    }
    
    /* עיצוב כותרות */
    h1, h2, h3 { color: #1a1a1a; font-weight: 800; }
    
    /* התאמות למובייל */
    @media (max-width: 640px) {
        .stMetric { margin-bottom: 10px; }
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ניהול עוגיות וחיבור נתונים ---
cookie_manager = stx.CookieManager()
conn = st.connection("gsheets", type=GSheetsConnection)

def get_all_data():
    u_cols = ['name', 'pin', 'role']
    t_cols = ['timestamp', 'name', 'type', 'amount', 'status', 'notes']
    try:
        u_df = conn.read(worksheet="Users", ttl=600).fillna("")
        t_df = conn.read(worksheet="Transactions", ttl=600).fillna("")
        s_df = conn.read(worksheet="Settings", ttl=600).fillna("")
        i_df = conn.read(worksheet="Inventory", ttl=600).fillna(0)
        
        # ניקוי נתונים
        for df, cols in [(u_df, u_cols), (t_df, t_cols)]:
            for col in cols:
                if col not in df.columns: df[col] = ""
        
        if not u_df.empty:
            u_df['name'] = u_df['name'].astype(str).str.strip()
            u_df['pin'] = u_df['pin'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        
        price = 2.5
        if not s_df.empty and 'key' in s_df.columns:
            p_row = s_df[s_df['key'] == 'bottle_price']
            if not p_row.empty: price = float(p_row['value'].values[0])
            
        return u_df, t_df, price, i_df
    except:
        return pd.DataFrame(columns=u_cols), pd.DataFrame(columns=t_cols), 2.5, pd.DataFrame()

users_df, trans_df, bottle_price, inv_df = get_all_data()

# --- 3. לוגיקת התחברות ---
if "logout_in_progress" not in st.session_state:
    st.session_state.logout_in_progress = False

if "user" not in st.session_state and not st.session_state.logout_in_progress:
    saved_name = cookie_manager.get(cookie="soda_user_name")
    if saved_name and not users_df.empty:
        user_match = users_df[users_df["name"] == saved_name]
        if not user_match.empty:
            st.session_state.user = user_match.iloc[0].to_dict()
            st.rerun()

def safe_update(worksheet_name, updated_data):
    try:
        conn.update(worksheet=worksheet_name, data=updated_data)
        st.cache_data.clear()
        return True
    except:
        st.error("שגיאת עדכון: נסה שוב בעוד דקה.")
        return False

# --- 4. ממשק משתמש ---
if "user" not in st.session_state:
    st.markdown("<h1 style='text-align: center; color: #1565C0;'>🥤 SodaClub</h1>", unsafe_allow_html=True)
    with st.container():
        st.write("---")
        u_list = users_df["name"].tolist() if not users_df.empty else []
        login_name = st.selectbox("מי מגיע לשתות?", u_list, index=None, placeholder="בחר שם...")
        login_pin = st.text_input("קוד אישי (PIN)", type="password")
        if st.button("התחברות למערכת", use_container_width=True, type="primary"):
            if login_name:
                u_match = users_df[users_df["name"] == login_name]
                if not u_match.empty and str(login_pin).strip() == u_match.iloc[0]["pin"]:
                    st.session_state.user = u_match.iloc[0].to_dict()
                    st.session_state.logout_in_progress = False
                    cookie_manager.set("soda_user_name", login_name, expires_at=datetime.now().replace(year=datetime.now().year + 1))
                    st.cache_data.clear()
                    st.rerun()
                else: st.error("קוד לא נכון.")
else:
    curr_user = st.session_state.user
    is_admin = curr_user.get('role') == 'admin'
    
    tabs = st.tabs(["👤 המשתמש שלי", "📊 ניהול ומלאי"]) if is_admin else [st.container()]

    with tabs[0]:
        st.markdown(f"### שלום, {curr_user['name']} 👋")
        
        # חישוב יתרה
        u_t = trans_df[trans_df["name"] == curr_user["name"]] if not trans_df.empty else pd.DataFrame()
        p_sum = u_t[u_t["type"] == "purchase"]["amount"].sum()
        pay_sum = u_t[(u_t["type"] == "payment") & (u_t["status"] == "completed")]["amount"].sum()
        adj_sum = u_t[u_t["type"] == "adjustment"]["amount"].sum()
        pend_sum = u_t[(u_t["type"] == "payment") & (u_t["status"] == "pending")]["amount"].sum()
        
        current_debt = p_sum + adj_sum - pay_sum
        
        c1, c2, c3 = st.columns(3)
        c1.metric("חוב מצטבר", f"₪{current_debt:.2f}")
        c2.metric("מחיר ליחידה", f"₪{bottle_price}")
        if pend_sum > 0: c3.warning(f"באישור: ₪{pend_sum}")

        st.write("---")
        
        # אזור רכישה מעוצב
        st.markdown("<div class='main-button'>", unsafe_allow_html=True)
        col_q1, col_q2 = st.columns([1, 3])
        buy_qty = col_q1.number_input("כמות", min_value=1, value=1)
        total_p = buy_qty * bottle_price
        if col_q2.button(f"קנה {buy_qty} בקבוקים (₪{total_p:.2f})", use_container_width=True):
            new_r = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "name": curr_user["name"], "type": "purchase", "amount": total_p, "status": "completed", "notes": ""}])
            if safe_update("Transactions", pd.concat([trans_df, new_r], ignore_index=True)): st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

        with st.expander("💰 הטענת תקציב / הפקדה"):
            with st.form("dep_f", clear_on_submit=True):
                amt = st.number_input("סכום הפקדה (₪)", min_value=1.0, value=20.0)
                if st.form_submit_button("שלח דיווח למנהל"):
                    new_r = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "name": curr_user["name"], "type": "payment", "amount": amt, "status": "pending", "notes": ""}])
                    if safe_update("Transactions", pd.concat([trans_df, new_r], ignore_index=True)): st.rerun()

        st.write("---")
        if st.button("🚪 התנתקות מהמכשיר", type="secondary"):
            cookie_manager.delete("soda_user_name")
            st.session_state.logout_in_progress = True
            if "user" in st.session_state: del st.session_state.user
            st.cache_data.clear()
            st.rerun()

    if is_admin:
        with tabs[1]:
            st.subheader("🛠️ כלי ניהול")
            
            # אישור הפקדות
            pend_df = trans_df[trans_df["status"] == "pending"]
            if not pend_df.empty:
                st.info(f"יש {len(pend_df)} הפקדות שמחכות לאישור")
                for idx, row in pend_df.iterrows():
                    ca, cb = st.columns([3, 1])
                    ca.write(f"**{row['name']}**: ₪{row['amount']}")
                    if cb.button("אשר", key=f"ap_{idx}"):
                        trans_df.at[idx, "status"] = "completed"
                        if safe_update("Transactions", trans_df): st.rerun()
            
            col_admin1, col_admin2 = st.columns(2)
            with col_admin1:
                st.write("**מצב מלאי**")
                taken = len(trans_df[trans_df['type'] == 'purchase'])
                stock = inv_df['quantity'].sum() - taken
                st.metric("בקבוקים במקרר", int(stock))
                with st.popover("עדכון מלאי (+/-)"):
                    q_c = st.number_input("שינוי", value=0)
                    if st.button("עדכן"):
                        new_i = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "quantity": q_c}])
                        if safe_update("Inventory", pd.concat([inv_df, new_i], ignore_index=True)): st.rerun()
            
            with col_admin2:
                st.write("**הגדרות מחיר**")
                st.write(f"נוכחי: ₪{bottle_price}")
                with st.popover("שנה מחיר"):
                    new_pr = st.number_input("מחיר חדש", value=bottle_price)
                    if st.button("שמור"):
                        s_df_new = conn.read(worksheet="Settings", ttl=0)
                        s_df_new.loc[s_df_new['key'] == 'bottle_price', 'value'] = new_pr
                        if safe_update("Settings", s_df_new): st.rerun()

            st.divider()
            st.subheader("📋 טבלת חובות כללית")
            all_sums = []
            for _, u in users_df.iterrows():
                b, _ = current_debt, 0 # שימוש בפונקציה מהקוד הקודם לחישוב מדויק
                u_t_all = trans_df[trans_df["name"] == u["name"]]
                d = u_t_all[u_t_all["type"] == "purchase"]["amount"].sum() + u_t_all[u_t_all["type"] == "adjustment"]["amount"].sum() - u_t_all[(u_t_all["type"] == "payment") & (u_t_all["status"] == "completed")]["amount"].sum()
                all_sums.append({"שם": u["name"], "חוב (₪)": f"{d:.2f}"})
            st.table(pd.DataFrame(all_sums).sort_values("חוב (₪)", ascending=False))

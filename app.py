import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import extra_streamlit_components as stx

# --- 1. הגדרות עמוד ותמיכה בעברית (RTL) ---
st.set_page_config(page_title="מועדון סודה PRO", layout="centered")

st.markdown("""
    <style>
    .stApp { direction: rtl; text-align: right; }
    div[data-testid="stForm"] { direction: rtl; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; height: 3.5em; }
    [data-testid="stMetricValue"] { font-size: 28px; color: #1E88E5; }
    .stTabs [data-baseweb="tab-list"] { direction: rtl; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ניהול עוגיות ---
cookie_manager = stx.CookieManager()

# --- 3. חיבור וטעינת נתונים ---
conn = st.connection("gsheets", type=GSheetsConnection)

def get_all_data():
    u_cols = ['name', 'pin', 'role']
    t_cols = ['timestamp', 'name', 'type', 'amount', 'status']
    try:
        u_df = conn.read(worksheet="Users", ttl=600).fillna("")
        t_df = conn.read(worksheet="Transactions", ttl=600).fillna("")
        s_df = conn.read(worksheet="Settings", ttl=600).fillna("")
        i_df = conn.read(worksheet="Inventory", ttl=600).fillna(0)
        
        for col in u_cols:
            if col not in u_df.columns: u_df[col] = ""
        for col in t_cols:
            if col not in t_df.columns: t_df[col] = ""
            
        if not u_df.empty:
            u_df['name'] = u_df['name'].astype(str).str.strip()
            u_df['pin'] = u_df['pin'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        
        price = 2.5
        if not s_df.empty and 'key' in s_df.columns:
            p_row = s_df[s_df['key'] == 'bottle_price']
            if not p_row.empty: price = float(p_row['value'].values[0])
            
        return u_df, t_df, price, i_df
    except Exception:
        return pd.DataFrame(columns=u_cols), pd.DataFrame(columns=t_cols), 2.5, pd.DataFrame()

users_df, trans_df, bottle_price, inv_df = get_all_data()

# --- 4. לוגיקת התחברות אוטומטית ---
if "logout_in_progress" not in st.session_state:
    st.session_state.logout_in_progress = False

if "user" not in st.session_state and not st.session_state.logout_in_progress:
    saved_name = cookie_manager.get(cookie="soda_user_name")
    if saved_name and not users_df.empty:
        user_match = users_df[users_df["name"] == saved_name]
        if not user_match.empty:
            st.session_state.user = user_match.iloc[0].to_dict()
            st.rerun()

# --- 5. פונקציית עזר לעדכון בטוח ---
def safe_update(worksheet_name, updated_data):
    try:
        conn.update(worksheet=worksheet_name, data=updated_data)
        st.cache_data.clear()
        return True
    except Exception:
        st.error("שגיאת עדכון: גוגל חסם את הבקשה זמנית (עומס). נסה שוב בעוד דקה.")
        return False

# --- 6. ממשק משתמש ---
if "user" not in st.session_state:
    st.header("🥤 מועדון סודה")
    with st.form("login_form"):
        u_list = users_df["name"].tolist() if not users_df.empty else []
        # שימוש ב-index=None ו-placeholder כדי שלא יופיע השם הראשון אוטומטית
        login_name = st.selectbox("בחר שם מהרשימה", u_list, index=None, placeholder="לחץ כאן לבחירת שם...")
        login_pin = st.text_input("קוד אישי", type="password")
        if st.form_submit_button("כניסה"):
            if not login_name:
                st.warning("בבקשה בחר שם מהרשימה.")
            else:
                u_match = users_df[users_df["name"] == login_name]
                if not u_match.empty and str(login_pin).strip() == u_match.iloc[0]["pin"]:
                    st.session_state.user = u_match.iloc[0].to_dict()
                    st.session_state.logout_in_progress = False
                    cookie_manager.set("soda_user_name", login_name, expires_at=datetime.now().replace(year=datetime.now().year + 1))
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("פרטים לא נכונים.")
else:
    user = st.session_state.user
    is_admin = user.get('role') == 'admin'
    tabs = st.tabs(["👤 המועדון שלי", "🛠️ ניהול"]) if is_admin else [st.container()]

    with tabs[0]:
        st.title(f"שלום, {user['name']} 👋")
        u_t = trans_df[trans_df["name"] == user["name"]] if not trans_df.empty else pd.DataFrame()
        
        purchases = u_t[u_t["type"] == "purchase"]["amount"].sum() if "type" in u_t.columns else 0
        payments = u_t[(u_t["type"] == "payment") & (u_t["status"] == "completed")]["amount"].sum() if "status" in u_t.columns else 0
        pending = u_t[(u_t["type"] == "payment") & (u_t["status"] == "pending")]["amount"].sum() if "status" in u_t.columns else 0
        
        balance = purchases - payments
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("חוב נוכחי", f"₪{balance:.2f}")
        col_m2.metric("מחיר בקבוק", f"₪{bottle_price}")
        if pending > 0: col_m3.warning(f"באישור: ₪{pending}")

        st.divider()

        # קניית סודה עם אפשרות לכמות מרובה
        with st.expander("🥤 לקחתי בקבוק סודה", expanded=True):
            col_q1, col_q2 = st.columns([1, 2])
            qty = col_q1.number_input("כמות", min_value=1, value=1, step=1)
            total_cost = qty * bottle_price
            if col_q2.button(f"אשר קניית {qty} בקבוקים (₪{total_cost:.2f})", type="primary"):
                new_r = pd.DataFrame([{
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                    "name": user["name"], "type": "purchase", 
                    "amount": total_cost, "status": "completed"
                }])
                if safe_update("Transactions", pd.concat([trans_df, new_r], ignore_index=True)):
                    st.rerun()
        
        with st.expander("💳 טעינת יתרה (הפקדה)"):
            with st.form("pay_f", clear_on_submit=True):
                # ברירת מחדל של 20 שקל כפי שביקשת
                p_amt = st.number_input("סכום להפקדה (₪)", min_value=1.0, value=20.0, step=1.0)
                if st.form_submit_button("שלח בקשה למנהל"):
                    new_r = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "name": user["name"], "type": "payment", "amount": p_amt, "status": "pending"}])
                    if safe_update("Transactions", pd.concat([trans_df, new_r], ignore_index=True)):
                        st.rerun()

        if st.button("🚪 התנתק"):
            cookie_manager.delete("soda_user_name")
            st.session_state.logout_in_progress = True
            if "user" in st.session_state: del st.session_state.user
            st.cache_data.clear()
            st.rerun()

    if is_admin:
        with tabs[1]:
            st.header("ניהול")
            st.subheader("💳 הפקדות לאישור")
            p_df = trans_df[trans_df["status"] == "pending"] if "status" in trans_df.columns else pd.DataFrame()
            if not p_df.empty:
                for idx, row in p_df.iterrows():
                    cp1, cp2 = st.columns([3, 1])
                    cp1.write(f"**{row['name']}**: ₪{row['amount']}")
                    if cp2.button("אשר", key=f"ap_{idx}"):
                        trans_df.at[idx, "status"] = "completed"
                        if safe_update("Transactions", trans_df): st.rerun()
            else: st.write("אין הפקדות ממתינות.")

            st.divider()
            col_manage1, col_manage2 = st.columns(2)
            with col_manage1:
                st.subheader("מלאי")
                # חישוב המלאי מתבצע לפי כמות הטרנזקציות מסוג purchase בגיליון (זה תמיד מדויק)
                bottles_taken = len(trans_df[trans_df['type'] == 'purchase'])
                st_count = inv_df['quantity'].sum() - bottles_taken if not inv_df.empty else 0
                st.metric("במקרר", int(st_count))
                with st.expander("עדכון מלאי (+/-)"):
                    with st.form("inv_f"):
                        q_c = st.number_input("שינוי כמות (חיובי להוספה, שלילי להפחתה)", value=0)
                        if st.form_submit_button("עדכן מלאי"):
                            if q_c != 0:
                                new_i = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "quantity": q_c}])
                                if safe_update("Inventory", pd.concat([inv_df, new_i], ignore_index=True)): st.rerun()
            
            with col_manage2:
                st.subheader("מחיר בקבוק")
                with st.expander("שנה מחיר"):
                    with st.form("price_form"):
                        np = st.number_input("מחיר חדש", value=bottle_price, step=0.5)
                        if st.form_submit_button("שמור"):
                            s_new = conn.read(worksheet="Settings", ttl=0)
                            s_new.loc[s_new['key'] == 'bottle_price', 'value'] = np
                            if safe_update("Settings", s_new): st.rerun()

            with st.expander("👤 הוספת משתמש"):
                with st.form("add_u"):
                    n_n = st.text_input("שם מלא")
                    n_p = st.text_input("קוד (4 ספרות)")
                    n_r = st.selectbox("תפקיד", ["user", "admin"])
                    if st.form_submit_button("הוסף"):
                        if n_n and len(n_p) == 4:
                            new_u = pd.DataFrame([{"name": n_n, "pin": n_p, "role": n_r}])
                            if safe_update("Users", pd.concat([users_df, new_u], ignore_index=True)): st.rerun()

            st.subheader("טבלת חובות")
            if not users_df.empty:
                sums = []
                for _, u in users_df.iterrows():
                    ut = trans_df[trans_df["name"] == u["name"]] if not trans_df.empty else pd.DataFrame()
                    d = ut[ut["type"] == "purchase"]["amount"].sum() - ut[(ut["type"] == "payment") & (ut["status"] == "completed")]["amount"].sum() if not ut.empty else 0
                    sums.append({"שם": u["name"], "חוב": f"{d:.2f}"})
                st.table(pd.DataFrame(sums).sort_values("חוב", ascending=False))

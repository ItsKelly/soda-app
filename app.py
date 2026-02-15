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
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; height: 3em; }
    [data-testid="stMetricValue"] { font-size: 28px; color: #1E88E5; }
    .stTabs [data-baseweb="tab-list"] { direction: rtl; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ניהול עוגיות (Persistent Login) ---
cookie_manager = stx.CookieManager()

# --- 3. חיבור וטעינת נתונים ---
conn = st.connection("gsheets", type=GSheetsConnection)

def get_all_data():
    try:
        # טעינה עם TTL של 10 שניות ליציבות ה-API
        u_df = conn.read(worksheet="Users", ttl="10s").fillna("")
        t_df = conn.read(worksheet="Transactions", ttl="10s").fillna("")
        s_df = conn.read(worksheet="Settings", ttl="10s").fillna("")
        i_df = conn.read(worksheet="Inventory", ttl="10s").fillna(0)
        
        # ניקוי בסיסי
        u_df['name'] = u_df['name'].astype(str).str.strip()
        u_df['email'] = u_df['email'].astype(str).str.strip()
        u_df['pin'] = u_df['pin'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        t_df['amount'] = pd.to_numeric(t_df['amount'], errors='coerce').fillna(0)
        i_df['quantity'] = pd.to_numeric(i_df['quantity'], errors='coerce').fillna(0)
        
        try:
            p_row = s_df[s_df['key'] == 'bottle_price']
            price = float(p_row['value'].values[0]) if not p_row.empty else 2.5
        except:
            price = 2.5
            
        return u_df, t_df, price, i_df
    except Exception as e:
        st.error(f"שגיאת טעינה: {e}")
        return pd.DataFrame(), pd.DataFrame(), 2.5, pd.DataFrame()

users_df, trans_df, bottle_price, inv_df = get_all_data()

# --- 4. לוגיקת התחברות אוטומטית ---
if "user" not in st.session_state:
    saved_email = cookie_manager.get(cookie="soda_user_email")
    if saved_email and not users_df.empty:
        user_match = users_df[users_df["email"] == saved_email]
        if not user_match.empty:
            st.session_state.user = user_match.iloc[0].to_dict()
            st.rerun()

# --- 5. ממשק משתמש ---
if "user" not in st.session_state:
    st.header("🥤 מועדון סודה - כניסה")
    with st.form("login_form"):
        u_list = users_df["name"].tolist() if not users_df.empty else ["טוען..."]
        u_name = st.selectbox("בחר שם", u_list)
        u_pin = st.text_input("קוד אישי", type="password")
        if st.form_submit_button("כניסה"):
            u_match = users_df[users_df["name"] == u_name]
            if not u_match.empty and str(u_pin).strip() == u_match.iloc[0]["pin"]:
                u_data = u_match.iloc[0].to_dict()
                st.session_state.user = u_data
                # הגדרת עוגיה לשנה
                cookie_manager.set("soda_user_email", u_data['email'], expires_at=datetime.now().replace(year=datetime.now().year + 1))
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("קוד שגוי.")
else:
    curr_user = st.session_state.user
    is_admin = curr_user.get('role') == 'admin'
    
    # הגדרת טאבים
    main_tabs = st.tabs(["👤 המועדון שלי", "🛠️ ניהול"]) if is_admin else [st.container()]

    # --- טאב אישי ---
    with main_tabs[0]:
        st.title(f"שלום, {curr_user['name']} 👋")
        
        # חישוב יתרה וחוב
        u_t = trans_df[trans_df["email"] == curr_user["email"]]
        purchases = u_t[u_t["type"] == "purchase"]["amount"].sum()
        payments = u_t[(u_t["type"] == "payment") & (u_t["status"] == "completed")]["amount"].sum()
        pending = u_t[(u_t["type"] == "payment") & (u_t["status"] == "pending")]["amount"].sum()
        
        balance = purchases - payments
        
        c1, c2, c3 = st.columns(3)
        c1.metric("חוב נוכחי", f"₪{balance:.2f}")
        c2.metric("מחיר בקבוק", f"₪{bottle_price}")
        if pending > 0:
            c3.warning(f"באישור: ₪{pending}")

        st.divider()

        if st.button("🥤 לקחתי בקבוק סודה", type="primary"):
            new_r = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "email": curr_user["email"], "type": "purchase", "amount": bottle_price, "status": "completed"}])
            conn.update(worksheet="Transactions", data=pd.concat([trans_df, new_r], ignore_index=True))
            st.cache_data.clear()
            st.rerun()
        
        with st.expander("💳 טעינת כסף (הפקדה)"):
            with st.form("pay_form", clear_on_submit=True):
                p_amt = st.number_input("סכום (₪)", min_value=1.0, value=10.0, step=1.0)
                if st.form_submit_button("שלח בקשת טעינה"):
                    new_r = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "email": curr_user["email"], "type": "payment", "amount": p_amt, "status": "pending"}])
                    conn.update(worksheet="Transactions", data=pd.concat([trans_df, new_r], ignore_index=True))
                    st.cache_data.clear()
                    st.rerun()

        st.subheader("היסטוריית פעולות")
        if not u_t.empty:
            st.dataframe(u_t.sort_values("timestamp", ascending=False), use_container_width=True)
        
        if st.button("🚪 התנתק"):
            cookie_manager.delete("soda_user_email")
            del st.session_state.user
            st.rerun()

    # --- טאב ניהול ---
    if is_admin:
        with main_tabs[1]:
            st.header("ניהול")
            
            # אישור הפקדות
            st.subheader("💳 הפקדות לאישור")
            pend_df = trans_df[trans_df["status"] == "pending"]
            if not pend_df.empty:
                for idx, row in pend_df.iterrows():
                    u_n = users_df[users_df["email"] == row["email"]]["name"].iloc[0]
                    cp1, cp2 = st.columns([3, 1])
                    cp1.write(f"**{u_n}**: ₪{row['amount']}")
                    if cp2.button("אשר", key=f"ap_{idx}"):
                        trans_df.at[idx, "status"] = "completed"
                        conn.update(worksheet="Transactions", data=trans_df)
                        st.cache_data.clear()
                        st.rerun()
            else:
                st.write("אין הפקדות.")

            st.divider()

            # הוספת משתמש
            with st.expander("👤 הוספת משתמש"):
                with st.form("add_u"):
                    n_n = st.text_input("שם")
                    n_e = st.text_input("מייל")
                    n_p = st.text_input("קוד (4 ספרות)")
                    n_r = st.selectbox("תפקיד", ["user", "admin"])
                    if st.form_submit_button("הוסף"):
                        if n_n and n_e and len(n_p) == 4:
                            new_u = pd.DataFrame([{"name": n_n, "email": n_e, "pin": n_p, "role": n_r}])
                            conn.update(worksheet="Users", data=pd.concat([users_df, new_u], ignore_index=True))
                            st.cache_data.clear()
                            st.rerun()

            st.divider()

            # מלאי ומחיר
            col_manage1, col_manage2 = st.columns(2)
            with col_manage1:
                st.subheader("מלאי")
                st_count = inv_df['quantity'].sum() - len(trans_df[trans_df['type'] == 'purchase'])
                st.metric("במקרר", int(st_count))
                with st.expander("הוסף מלאי"):
                    with st.form("inv_f"):
                        q_add = st.number_input("כמות", min_value=1, value=24)
                        if st.form_submit_button("עדכן"):
                            new_i = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "quantity": q_add}])
                            conn.update(worksheet="Inventory", data=pd.concat([inv_df, new_i], ignore_index=True))
                            st.cache_data.clear()
                            st.rerun()
            
            with col_manage2:
                st.subheader("מחיר")
                st.write(f"נוכחי: ₪{bottle_price}")
                with st.expander("שנה מחיר"):
                    with st.form("pr_f"):
                        np = st.number_input("מחיר חדש", value=bottle_price, step=0.5)
                        if st.form_submit_button("שמור"):
                            s_new = conn.read(worksheet="Settings", ttl=0)
                            s_new.loc[s_new['key'] == 'bottle_price', 'value'] = np
                            conn.update(worksheet="Settings", data=s_new)
                            st.cache_data.clear()
                            st.rerun()

            st.subheader("חובות")
            sums = []
            for _, u in users_df.iterrows():
                ut = trans_df[trans_df["email"] == u["email"]]
                d = ut[ut["type"] == "purchase"]["amount"].sum() - ut[(ut["type"] == "payment") & (ut["status"] == "completed")]["amount"].sum()
                sums.append({"שם": u["name"], "₪": f"{d:.2f}"})
            st.table(pd.DataFrame(sums).sort_values("₪", ascending=False))

import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import extra_streamlit_components as stx

# --- 1. הגדרות עמוד ותמיכה בעברית (RTL) ---
st.set_page_config(page_title="מועדון סודה - גרסה קלה", layout="centered")

st.markdown("""
    <style>
    .stApp { direction: rtl; text-align: right; }
    div[data-testid="stForm"] { direction: rtl; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; height: 3.5em; background-color: #1E88E5; color: white; }
    [data-testid="stMetricValue"] { font-size: 28px; color: #1E88E5; }
    .stTabs [data-baseweb="tab-list"] { direction: rtl; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ניהול עוגיות (Login עמיד לפי שם) ---
cookie_manager = stx.CookieManager()

# --- 3. חיבור וטעינת נתונים ---
conn = st.connection("gsheets", type=GSheetsConnection)

def get_all_data():
    # יצירת מבנה ריק למניעת קריסות (KeyError)
    empty_users = pd.DataFrame(columns=['name', 'pin', 'role'])
    empty_trans = pd.DataFrame(columns=['timestamp', 'name', 'type', 'amount', 'status'])
    
    try:
        # TTL גבוה למניעת שגיאת Rate Limit (429)
        u_df = conn.read(worksheet="Users", ttl=900).fillna("")
        t_df = conn.read(worksheet="Transactions", ttl=900).fillna("")
        s_df = conn.read(worksheet="Settings", ttl=900).fillna("")
        i_df = conn.read(worksheet="Inventory", ttl=900).fillna(0)
        
        if not u_df.empty:
            u_df['name'] = u_df['name'].astype(str).str.strip()
            u_df['pin'] = u_df['pin'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        
        if not t_df.empty:
            t_df['name'] = t_df['name'].astype(str).str.strip()
            t_df['amount'] = pd.to_numeric(t_df['amount'], errors='coerce').fillna(0)
            
        # שליפת מחיר בקבוק
        price = 2.5
        if not s_df.empty:
            p_row = s_df[s_df['key'] == 'bottle_price']
            if not p_row.empty:
                price = float(p_row['value'].values[0])
            
        return u_df, t_df, price, i_df
    except Exception as e:
        st.error("חל עומס זמני על השרת, המידע מוצג מהזיכרון.")
        return empty_users, empty_trans, 2.5, pd.DataFrame()

users_df, trans_df, bottle_price, inv_df = get_all_data()

# --- 4. לוגיקת התחברות אוטומטית (לפי שם) ---
if "user" not in st.session_state:
    saved_name = cookie_manager.get(cookie="soda_user_name")
    if saved_name and not users_df.empty:
        user_match = users_df[users_df["name"] == saved_name]
        if not user_match.empty:
            st.session_state.user = user_match.iloc[0].to_dict()
            st.rerun()

# --- 5. ממשק משתמש ---
if "user" not in st.session_state:
    st.header("🥤 מועדון סודה")
    with st.form("login_form"):
        u_list = users_df["name"].tolist() if not users_df.empty else ["טוען..."]
        login_name = st.selectbox("מי אתה?", u_list)
        login_pin = st.text_input("קוד אישי", type="password")
        if st.form_submit_button("כניסה"):
            u_match = users_df[users_df["name"] == login_name]
            if not u_match.empty and str(login_pin).strip() == u_match.iloc[0]["pin"]:
                user_data = u_match.iloc[0].to_dict()
                st.session_state.user = user_data
                # שמירת השם בעוגיה לשנה
                cookie_manager.set("soda_user_name", user_data['name'], expires_at=datetime.now().replace(year=datetime.now().year + 1))
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("קוד שגוי.")
else:
    user = st.session_state.user
    is_admin = user.get('role') == 'admin'
    
    tabs = st.tabs(["👤 המועדון שלי", "🛠️ ניהול"]) if is_admin else [st.container()]

    # --- טאב אישי ---
    with tabs[0]:
        st.title(f"שלום, {user['name']} 👋")
        
        # חישוב יתרה וחוב
        u_t = trans_df[trans_df["name"] == user["name"]] if not trans_df.empty else pd.DataFrame()
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
            new_r = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "name": user["name"], "type": "purchase", "amount": bottle_price, "status": "completed"}])
            conn.update(worksheet="Transactions", data=pd.concat([trans_df, new_r], ignore_index=True))
            st.cache_data.clear()
            st.rerun()
        
        with st.expander("💳 טעינת כסף (הפקדה)"):
            with st.form("pay_f", clear_on_submit=True):
                p_amt = st.number_input("סכום (₪)", min_value=1.0, value=10.0, step=1.0)
                if st.form_submit_button("שלח בקשת טעינה"):
                    new_r = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "name": user["name"], "type": "payment", "amount": p_amt, "status": "pending"}])
                    conn.update(worksheet="Transactions", data=pd.concat([trans_df, new_r], ignore_index=True))
                    st.cache_data.clear()
                    st.rerun()

        st.subheader("היסטוריה אישית")
        if not u_t.empty:
            st.dataframe(u_t.sort_values("timestamp", ascending=False), use_container_width=True)
        
        if st.button("🚪 התנתק והסר מהמכשיר"):
            cookie_manager.delete("soda_user_name")
            del st.session_state.user
            st.cache_data.clear()
            st.rerun()

    # --- טאב ניהול ---
    if is_admin:
        with tabs[1]:
            st.header("ניהול מועדון")
            
            # 1. אישור הפקדות
            st.subheader("💳 הפקדות לאישור")
            pend_df = trans_df[trans_df["status"] == "pending"] if "status" in trans_df.columns else pd.DataFrame()
            if not pend_df.empty:
                for idx, row in pend_df.iterrows():
                    cp1, cp2 = st.columns([3, 1])
                    cp1.write(f"**{row['name']}** - ₪{row['amount']}")
                    if cp2.button("אשר", key=f"ap_{idx}"):
                        trans_df.at[idx, "status"] = "completed"
                        conn.update(worksheet="Transactions", data=trans_df)
                        st.cache_data.clear()
                        st.rerun()
            else:
                st.write("אין הפקדות שמחכות.")

            st.divider()

            # 2. ניהול מלאי ומחיר
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                st.subheader("מלאי")
                st_count = inv_df['quantity'].sum() - len(trans_df[trans_df['type'] == 'purchase']) if not inv_df.empty else 0
                st.metric("במקרר", int(st_count))
                with st.expander("הוסף מלאי"):
                    with st.form("inv_form"):
                        q_add = st.number_input("כמות", min_value=1, value=24)
                        if st.form_submit_button("עדכן"):
                            new_i = pd.DataFrame([{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "quantity": q_add}])
                            conn.update(worksheet="Inventory", data=pd.concat([inv_df, new_i], ignore_index=True))
                            st.cache_data.clear()
                            st.rerun()
            
            with col_m2:
                st.subheader("מחיר")
                with st.expander("עדכן מחיר"):
                    with st.form("price_form"):
                        np = st.number_input("מחיר (₪)", value=bottle_price, step=0.5)
                        if st.form_submit_button("שמור"):
                            s_df_new = conn.read(worksheet="Settings", ttl=0)
                            if not s_df_new[s_df_new['key'] == 'bottle_price'].empty:
                                s_df_new.loc[s_df_new['key'] == 'bottle_price', 'value'] = np
                            else:
                                s_df_new = pd.concat([s_df_new, pd.DataFrame([{"key": "bottle_price", "value": np}])])
                            conn.update(worksheet="Settings", data=s_df_new)
                            st.cache_data.clear()
                            st.rerun()

            st.divider()

            # 3. הוספת משתמש
            with st.expander("👤 הוספת חבר מועדון"):
                with st.form("add_user"):
                    n_n = st.text_input("שם מלא (ייחודי)")
                    n_p = st.text_input("קוד (4 ספרות)")
                    n_r = st.selectbox("תפקיד", ["user", "admin"])
                    if st.form_submit_button("הוסף"):
                        if n_n and len(n_p) == 4:
                            new_u = pd.DataFrame([{"name": n_n, "pin": n_p, "role": n_r}])
                            conn.update(worksheet="Users", data=pd.concat([users_df, new_u], ignore_index=True))
                            st.cache_data.clear()
                            st.rerun()

            st.subheader("טבלת חובות")
            if not users_df.empty:
                sums = []
                for _, u in users_df.iterrows():
                    ut = trans_df[trans_df["name"] == u["name"]] if not trans_df.empty else pd.DataFrame()
                    d = ut[ut["type"] == "purchase"]["amount"].sum() - ut[(ut["type"] == "payment") & (ut["status"] == "completed")]["amount"].sum()
                    sums.append({"שם": u["name"], "חוב": f"{d:.2f}"})
                st.table(pd.DataFrame(sums).sort_values("חוב", ascending=False))

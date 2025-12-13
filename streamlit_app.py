import datetime
import os
import uuid

import pandas as pd
import streamlit as st

# App config
st.set_page_config(page_title="Card Tracker", page_icon="🟨🟥", layout="wide")

# Custom CSS for better styling
st.markdown("""
<style>
    .yellow-card {
        background-color: rgba(255, 243, 205, 0.3);
        padding: 10px;
        border-radius: 5px;
        border-left: 4px solid #ffc107;
        margin: 5px 0;
    }
    .red-card {
        background-color: rgba(248, 215, 218, 0.3);
        padding: 10px;
        border-radius: 5px;
        border-left: 4px solid #dc3545;
        margin: 5px 0;
    }
    .metric-card {
        background-color: rgba(240, 242, 246, 0.5);
        padding: 20px;
        border-radius: 10px;
        text-align: center;
        border: 1px solid rgba(0,0,0,0.1);
    }
    .warning-box {
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 15px;
        margin: 10px 0;
        border-radius: 5px;
    }
    .success-box {
        background-color: #d1e7dd;
        border-left: 4px solid #198754;
        padding: 15px;
        margin: 10px 0;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

st.title("🟨🟥 Barnett St Slacker Tracker")

# File paths
ROOT = os.path.dirname(__file__)
USERS_PKL = os.path.join(ROOT, "user_data.pkl")
USERS_CSV = os.path.join(ROOT, "user_data.csv")
TICKETS_PKL = os.path.join(ROOT, "tickets.pkl")
TICKETS_CSV = os.path.join(ROOT, "tickets.csv")

YELLOW_EXPIRE_DAYS = 30
YELLOW_WARNING_DAYS = 7  # Warn when yellow cards have less than 7 days left


def load_users():
    if os.path.exists(USERS_PKL):
        try:
            return pd.read_pickle(USERS_PKL)
        except Exception:
            pass
    if os.path.exists(USERS_CSV):
        df = pd.read_csv(USERS_CSV)
        try:
            df.to_pickle(USERS_PKL)
        except Exception:
            pass
        return df
    return pd.DataFrame(columns=["username", "display_name", "password"])


def load_tickets():
    if os.path.exists(TICKETS_PKL):
        try:
            df = pd.read_pickle(TICKETS_PKL)
            if "date_received" in df.columns:
                df["date_received"] = pd.to_datetime(df["date_received"])
            return df
        except Exception:
            pass
    if os.path.exists(TICKETS_CSV):
        df = pd.read_csv(TICKETS_CSV, parse_dates=["date_received"]) if os.path.getsize(TICKETS_CSV) > 0 else pd.DataFrame(
            columns=["id", "receiver", "card_type", "date_received", "submitted_by", "status", "note"]
        )
        try:
            df.to_pickle(TICKETS_PKL)
        except Exception:
            pass
        return df
    return pd.DataFrame(
        columns=["id", "receiver", "card_type", "date_received", "submitted_by", "status", "note"]
    )


def save_tickets(df):
    try:
        df.to_pickle(TICKETS_PKL)
    except Exception:
        df.to_csv(TICKETS_CSV, index=False)


def process_expirations_and_conversions(tickets):
    changed = False
    df = tickets.copy()
    today = pd.Timestamp(datetime.date.today())
    df["date_received"] = pd.to_datetime(df["date_received"]).dt.normalize()

    # Expire old yellows
    mask_yellow_active = (df["card_type"] == "Yellow") & (df["status"] == "active")
    expire_mask = mask_yellow_active & (df["date_received"] < (today - pd.Timedelta(days=YELLOW_EXPIRE_DAYS)))
    if expire_mask.any():
        df.loc[expire_mask, "status"] = "expired"
        changed = True

    # Convert groups of 3 active yellows into reds
    for user in df["receiver"].unique():
        user_mask = (df["receiver"] == user) & (df["card_type"] == "Yellow") & (df["status"] == "active")
        active_yellows = df[user_mask].sort_values("date_received")
        while len(active_yellows) >= 3:
            to_convert = active_yellows.iloc[:3]
            df.loc[df["id"].isin(to_convert["id"]), "status"] = "converted"

            new_red = {
                "id": str(uuid.uuid4()),
                "receiver": user,
                "card_type": "Red",
                "date_received": today.strftime("%Y-%m-%d"),
                "submitted_by": "system",
                "status": "active",
                "note": "Auto-converted from 3 yellows",
            }
            df = pd.concat([pd.DataFrame([new_red]), df], ignore_index=True)
            changed = True

            user_mask = (df["receiver"] == user) & (df["card_type"] == "Yellow") & (df["status"] == "active")
            active_yellows = df[user_mask].sort_values("date_received")

    df["date_received"] = pd.to_datetime(df["date_received"]).dt.date
    return df, changed


def get_days_until_expiry(date_received):
    """Calculate days until a yellow card expires"""
    if pd.isna(date_received):
        return None
    today = datetime.date.today()
    if isinstance(date_received, str):
        date_received = pd.to_datetime(date_received).date()
    expiry_date = date_received + datetime.timedelta(days=YELLOW_EXPIRE_DAYS)
    days_left = (expiry_date - today).days
    return days_left


def format_status_badge(status):
    """Return a formatted status badge"""
    if status == "active":
        return "🟢 Active"
    elif status == "expired":
        return "⚫ Expired"
    elif status == "converted":
        return "🔄 Converted"
    return status


users_df = load_users()
tickets_df = load_tickets()

# Initialize session state
if "user" not in st.session_state:
    st.session_state.user = None
if "tickets" not in st.session_state:
    st.session_state.tickets = tickets_df
if "show_success" not in st.session_state:
    st.session_state.show_success = None

# Process expirations/conversions on load
processed, changed = process_expirations_and_conversions(st.session_state.tickets)
if changed:
    st.session_state.tickets = processed
    save_tickets(processed)


def login_page():
    # Center the login form
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("### Login")
        
        if users_df.empty:
            st.error("No users found in user_data.csv. Please create users first.")
            return

        users_list = users_df["username"].tolist()
        if "admin" not in users_list:
            users_list.insert(0, "admin")
        
        with st.form("login_form"):
            username = st.selectbox("Username", users_list)
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True)

        if submitted:
            if username == "admin":
                if password == "adminpw":
                    st.session_state.user = "admin"
                    st.session_state.page = "Existing Cards"
                    st.rerun()
                else:
                    st.error("Invalid credentials")
                return

            user_row = users_df[users_df["username"] == username]
            if not user_row.empty and (pd.isna(user_row.iloc[0].get("password")) or password == user_row.iloc[0].get("password")):
                st.session_state.user = username
                st.session_state.page = "Add Card"
                st.rerun()
            else:
                st.error("Invalid credentials")


def logout():
    st.session_state.user = None
    st.session_state.show_success = None


def add_card_page():
    st.markdown("### Add a New Card")

    users = users_df["username"].tolist()

    with st.form("add_card"):
        receiver = st.selectbox("Who receives the card?", users)
        card_type = st.radio(
            "Card type",
            ["Yellow", "Red"],
            horizontal=True,
            help="Yellow cards expire after 30 days. 3 Yellow cards auto-convert to 1 Red card.",
        )
        date_received = st.date_input("Date received", value=datetime.date.today())
        note = st.text_area("Note (optional)", height=100)
        submitted = st.form_submit_button("Submit Card", use_container_width=True, type="primary")

    if submitted:
        submitted_by = st.session_state.user

        new_ticket = {
            "id": str(uuid.uuid4()),
            "receiver": receiver,
            "card_type": card_type,
            "date_received": date_received.strftime("%Y-%m-%d"),
            "submitted_by": submitted_by,
            "status": "active",
            "note": note,
        }
        st.session_state.tickets = pd.concat([pd.DataFrame([new_ticket]), st.session_state.tickets], ignore_index=True)

        processed, changed = process_expirations_and_conversions(st.session_state.tickets)
        st.session_state.tickets = processed
        save_tickets(processed)

        st.session_state.show_success = f"✅ {card_type} card added for {receiver}"
        st.session_state.page = "Existing Cards"
        st.rerun()
    
    # Display quick tips
    st.info("**Quick Tips:**\n\n- Yellow cards expire in 30 days\n- 3 Yellow → 1 Red (automatic)\n- Red cards are penalties")

def existing_cards_page():
    # Show success message if present
    if st.session_state.show_success:
        st.success(st.session_state.show_success)
        st.session_state.show_success = None
    
    st.markdown("### Cards Dashboard")
    
    df = st.session_state.tickets.copy()
    df["date_received"] = pd.to_datetime(df["date_received"]).dt.date

    # Calculate all-time statistics for biggest slackers
    slacker_data = []
    for u in users_df["username"]:
        user_rows = df[df["receiver"] == u]
        total_yellows = len(user_rows[user_rows["card_type"] == "Yellow"])
        total_reds = len(user_rows[user_rows["card_type"] == "Red"])
        slacker_score = total_yellows + (total_reds * 3)  # Weight reds more heavily
        
        slacker_data.append({
            "username": u,
            "total_yellows": total_yellows,
            "total_reds": total_reds,
            "slacker_score": slacker_score
        })
    
    slacker_df = pd.DataFrame(slacker_data).sort_values("slacker_score", ascending=False)
    
    # Display Biggest Slackers
    st.markdown("#### 🏆 Biggest Slackers (All Time)")
    
    # Only show slackers who have at least one card
    slacker_df_filtered = slacker_df[slacker_df["slacker_score"] > 0]
    
    if len(slacker_df_filtered) > 0:
        cols = st.columns(min(len(slacker_df_filtered), 5))
        for idx, (_, row) in enumerate(slacker_df_filtered.head(5).iterrows()):
            with cols[idx]:
                medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][idx]
                st.markdown(f"""
                <div style='background-color: rgba(240, 242, 246, 0.5); padding: 15px; border-radius: 10px; text-align: center; border: 1px solid rgba(0,0,0,0.1);'>
                    <h3 style='margin: 0;'>{medal}</h3>
                    <h4 style='margin: 5px 0;'>{row['username']}</h4>
                    <p style='margin: 5px 0; color: #ffc107;'><strong>🟨 {int(row['total_yellows'])}</strong></p>
                    <p style='margin: 5px 0; color: #dc3545;'><strong>🟥 {int(row['total_reds'])}</strong></p>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("No cards have been issued yet.")
    
    st.markdown("---")

    # Summary metrics
    summary_data = []
    for u in users_df["username"]:
        user_rows = df[df["receiver"] == u]
        active_yellows = len(user_rows[(user_rows["card_type"] == "Yellow") & (user_rows["status"] == "active")])
        active_reds = len(user_rows[(user_rows["card_type"] == "Red") & (user_rows["status"] == "active")])
        
        # Check for cards about to expire
        yellows_expiring = 0
        if active_yellows > 0:
            yellow_rows = user_rows[(user_rows["card_type"] == "Yellow") & (user_rows["status"] == "active")]
            for _, row in yellow_rows.iterrows():
                days_left = get_days_until_expiry(row["date_received"])
                if days_left is not None and 0 < days_left <= YELLOW_WARNING_DAYS:
                    yellows_expiring += 1
        
        summary_data.append({
            "username": u,
            "yellow_active": active_yellows,
            "red_active": active_reds,
            "penalties": active_reds,
            "yellows_expiring": yellows_expiring
        })

    summary_df = pd.DataFrame(summary_data)
    
    # Display metrics in columns
    st.markdown("#### User Summary")
    
    # Create detailed summary cards
    for idx, row in summary_df.iterrows():
        user = row['username']
        with st.expander(f"**{user}** — Active: 🟨 {row['yellow_active']} | 🟥 {row['red_active']} | Penalties: {row['penalties']}", expanded=False):
            cols = st.columns(4)
            
            with cols[0]:
                st.metric("🟨 Yellow Cards", row['yellow_active'])
            with cols[1]:
                st.metric("🟥 Red Cards", row['red_active'])
            with cols[2]:
                st.metric("⚠️ Penalties", row['penalties'])
            with cols[3]:
                if row['yellows_expiring'] > 0:
                    st.metric("⏰ Expiring Soon", row['yellows_expiring'])
                else:
                    st.metric("⏰ Expiring Soon", "None")
            
            # Show warning if cards are expiring
            if row['yellows_expiring'] > 0:
                st.warning(f"⚠️ {row['yellows_expiring']} yellow card(s) expiring within {YELLOW_WARNING_DAYS} days!")
            
            # Show active cards for this user
            user_active_cards = df[(df["receiver"] == user) & (df["status"] == "active")].sort_values("date_received", ascending=False)
            
            if len(user_active_cards) > 0:
                st.markdown("**Active Cards:**")
                
                for _, card in user_active_cards.iterrows():
                    card_type_emoji = "🟨" if card["card_type"] == "Yellow" else "🟥"
                    days_left = get_days_until_expiry(card["date_received"]) if card["card_type"] == "Yellow" else None
                    
                    # Color code based on expiry
                    if days_left is not None:
                        if days_left <= YELLOW_WARNING_DAYS:
                            bg_color = "#fff3cd"
                            border_color = "#ffc107"
                        else:
                            bg_color = "rgba(255, 243, 205, 0.3)"
                            border_color = "#ffc107"
                    else:
                        bg_color = "rgba(248, 215, 218, 0.3)"
                        border_color = "#dc3545"
                    
                    expiry_text = f" | Expires in {days_left} days" if days_left is not None else ""
                    note_text = f" | Note: {card['note']}" if pd.notna(card['note']) and card['note'].strip() != "" else ""
                    
                    st.markdown(f"""
                    <div style='background-color: {bg_color}; padding: 10px; border-radius: 5px; border-left: 4px solid {border_color}; margin: 5px 0;'>
                        <strong>{card_type_emoji} {card["card_type"]}</strong> — Received: {card["date_received"]}{expiry_text}{note_text}
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No active cards")

    st.markdown("---")
    # Prepare a display dataframe copy
    display_df = df.copy()

    display_df["days_until_expiry"] = display_df.apply(
        lambda row: get_days_until_expiry(row["date_received"]) if row["card_type"] == "Yellow" and row["status"] == "active" else None,
        axis=1
    )
    
    # Format status with badges
    display_df["status_badge"] = display_df["status"].apply(format_status_badge)
    
    # Reorder and select columns for display
    display_columns = ["receiver", "card_type", "status_badge", "date_received", "days_until_expiry", "submitted_by", "note"]
    display_df = display_df[display_columns]
    
    # Rename columns for better display
    display_df.columns = ["User", "Card Type", "Status", "Date Received", "Days Left", "Submitted By", "Note"]
    
    st.markdown(f"#### All Cards (Total: {len(display_df)})")
    
    # Style the dataframe
    def highlight_expiring(row):
        if row["Days Left"] is not None and 0 < row["Days Left"] <= YELLOW_WARNING_DAYS:
            return ['background-color: #fff3cd'] * len(row)
        return [''] * len(row)
    
    styled_df = display_df.sort_values("Date Received", ascending=False).reset_index(drop=True)
    
    st.dataframe(
        styled_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Card Type": st.column_config.TextColumn(
                "Card Type",
                help="Type of card issued"
            ),
            "Days Left": st.column_config.NumberColumn(
                "Days Left",
                help="Days until yellow card expires (active yellow cards only)",
                format="%d days"
            ),
            "Date Received": st.column_config.DateColumn(
                "Date Received",
                format="MMM DD, YYYY"
            )
        }
    )


def admin_page():
    st.markdown("### Admin — Manage Cards")
    
    df = st.session_state.tickets.copy()

    # Statistics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Cards", len(df))
    with col2:
        st.metric("🟢 Active Cards", len(df[df["status"] == "active"]))
    with col3:
        st.metric("⚫ Expired Cards", len(df[df["status"] == "expired"]))
    with col4:
        st.metric("🔄 Converted Cards", len(df[df["status"] == "converted"]))

    st.markdown("---")
    
    # Edit cards section
    with st.expander("Edit Cards", expanded=True):
        st.info("Make changes in the table below and click 'Save Changes' to apply them.")
        edited = st.data_editor(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "id": st.column_config.TextColumn("ID", disabled=True),
                "date_received": st.column_config.DateColumn("Date Received", format="YYYY-MM-DD"),
                "card_type": st.column_config.SelectboxColumn("Card Type", options=["Yellow", "Red"]),
                "status": st.column_config.SelectboxColumn("Status", options=["active", "expired", "converted"])
            }
        )
        
        col1, col2 = st.columns([1, 4])
        with col1:
            with st.form("save_changes_form"):
                save_submitted = st.form_submit_button("Save Changes", use_container_width=True, type="primary")
        
        if save_submitted:
            st.session_state.tickets = edited
            save_tickets(edited)
            st.success("✅ Changes saved successfully!")
            st.rerun()

    # Delete cards section
    with st.expander("Delete Cards"):
        st.warning("**Warning:** Deleted cards cannot be recovered!")
        
        ids = df["id"].tolist()
        card_labels = [f"{df.loc[df['id']==id, 'receiver'].values[0]} - {df.loc[df['id']==id, 'card_type'].values[0]} - {df.loc[df['id']==id, 'date_received'].values[0]}" for id in ids]
        
        with st.form("delete_form"):
            to_delete = st.multiselect(
                "Select cards to delete",
                options=ids,
                format_func=lambda x: card_labels[ids.index(x)]
            )
            
            col1, col2 = st.columns([1, 4])
            with col1:
                delete_submitted = st.form_submit_button("Delete Selected", use_container_width=True, type="secondary")
        
        if delete_submitted:
            if not to_delete:
                st.warning("No cards selected for deletion")
            else:
                new_df = df[~df["id"].isin(to_delete)].reset_index(drop=True)
                st.session_state.tickets = new_df
                save_tickets(new_df)
                st.success(f"✅ Successfully deleted {len(to_delete)} card(s)")
                st.rerun()


def main():
    if st.session_state.user is None:
        login_page()
        return

    # Sidebar
    with st.sidebar:
        st.markdown(f"### {st.session_state.user}")
        st.markdown("---")
        
        # Navigation
        pages = ["Existing Cards", "Add Card"]
        if st.session_state.user == "admin":
            pages.append("Admin")

        default_index = 0
        if "page" in st.session_state and st.session_state.page in pages:
            default_index = pages.index(st.session_state.page)

        page = st.radio("Navigation", pages, index=default_index, label_visibility="collapsed")
        st.session_state.page = page
        
        st.markdown("---")
        
        # Info box
        st.info(f"""
        **Card Rules:**
        - Yellow cards expire in {YELLOW_EXPIRE_DAYS} days
        - 3 Yellow cards = 1 Red card
        - Red cards are penalties
        """)
        
        st.markdown("---")
        
        if st.button("Logout", use_container_width=True):
            logout()
            st.rerun()

    # Main content
    if page == "Add Card":
        add_card_page()
    elif page == "Existing Cards":
        existing_cards_page()
    elif page == "Admin":
        admin_page()


if __name__ == "__main__":
    main()
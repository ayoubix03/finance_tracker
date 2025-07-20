import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import json
import os
import hashlib
import io
import logging
from datetime import datetime

# --- Constants ---
USERS_FILE = "users.json"
MASTER_PASSWORD = "ayoub2003"
CURRENCY = "MAD"

# Setup logging
logging.basicConfig(filename='finance_tracker.log', level=logging.INFO)

# --- Helper Functions ---
def format_currency(amount):
    """Format amount as MAD currency"""
    return f"{amount:,.2f} {CURRENCY}"

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(stored_hash, password):
    return stored_hash == hash_password(password)

def categorize_expense(description, categories):
    description = str(description).lower()
    for category, keywords in categories.items():
        for keyword in keywords:
            if keyword.lower() in description:
                return category
    return "Other"

def get_download_filename(username):
    today = datetime.now().strftime("%Y%m%d")
    return f"{username}_expenses_{today}.xlsx"

def get_excel_download_data(df):
    """Convert DataFrame to Excel bytes for download with fallback"""
    output = io.BytesIO()
    try:
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
    except ImportError:
        try:
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
        except ImportError:
            st.error("Please install either xlsxwriter or openpyxl for Excel export")
            return None
    return output.getvalue()

# --- File Handling ---
def ensure_directory_exists():
    """Ensure data directory structure exists"""
    try:
        os.makedirs('data/users', exist_ok=True)
        if not os.path.exists(os.path.join('data', USERS_FILE)):
            with open(os.path.join('data', USERS_FILE), 'w') as f:
                json.dump({}, f)
        return True
    except Exception as e:
        logging.error(f"Directory creation error: {str(e)}")
        st.error(f"Failed to initialize data storage: {str(e)}")
        return False

def safe_json_read(filepath, default=None):
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default
    except Exception as e:
        logging.error(f"Error reading {filepath}: {str(e)}")
        st.error(f"Error reading data: {str(e)}")
        return default

def safe_json_write(filepath, data):
    try:
        temp_file = filepath + ".tmp"
        with open(temp_file, 'w') as f:
            json.dump(data, f, indent=4)
        if os.path.exists(filepath):
            os.remove(filepath)
        os.rename(temp_file, filepath)
        return True
    except Exception as e:
        logging.error(f"Error writing to {filepath}: {str(e)}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        st.error(f"Error saving data: {str(e)}")
        return False

# --- User Management ---
def load_users():
    ensure_directory_exists()
    users = safe_json_read(os.path.join('data', USERS_FILE), {})
    
    # Fix any existing users that might be missing required files
    for username, user_data in users.items():
        if "balance_file" not in user_data:
            user_data["balance_file"] = f"user_{username}_balance.json"
            balance_file = os.path.join('data', 'users', user_data["balance_file"])
            if not os.path.exists(balance_file):
                safe_json_write(balance_file, {"balance": 0.0})
    
    safe_json_write(os.path.join('data', USERS_FILE), users)
    return users

def save_user(username, password):
    ensure_directory_exists()
    users = load_users()
    
    user_data = {
        "password_hash": hash_password(password),
        "data_file": f"user_{username}_data.csv",
        "categories_file": f"user_{username}_categories.json",
        "balance_file": f"user_{username}_balance.json"
    }
    
    try:
        user_dir = os.path.join('data', 'users')
        os.makedirs(user_dir, exist_ok=True)
        
        # Create empty data file
        data_file = os.path.join(user_dir, user_data["data_file"])
        pd.DataFrame(columns=['Date', 'Description', 'Category', 'Amount']).to_csv(data_file, index=False)
        
        # Create categories file
        categories_file = os.path.join(user_dir, user_data["categories_file"])
        default_categories = {
            "Food": ["grocery", "restaurant", "lunch"],
            "Transport": ["uber", "taxi", "gas"],
            "Entertainment": ["movie", "game", "concert"],
            "Bills": ["electric", "water", "internet"],
        }
        safe_json_write(categories_file, default_categories)
        
        # Create balance file
        balance_file = os.path.join(user_dir, user_data["balance_file"])
        safe_json_write(balance_file, {"balance": 0.0})
        
        # Update users.json
        users[username] = user_data
        safe_json_write(os.path.join('data', USERS_FILE), users)
        return True
    except Exception as e:
        logging.error(f"Error creating user {username}: {str(e)}")
        st.error(f"Failed to create account: {str(e)}")
        return False

# --- Balance Functions ---
def get_user_balance(username):
    users = load_users()
    if username not in users:
        return 0.0
        
    user_files = users[username]
    balance_file = os.path.join('data', 'users', user_files["balance_file"])
    
    try:
        if os.path.exists(balance_file):
            with open(balance_file, 'r') as f:
                return float(json.load(f).get("balance", 0.0))
        return 0.0
    except Exception as e:
        logging.error(f"Error reading balance for {username}: {str(e)}")
        return 0.0

def update_user_balance(username, amount):
    users = load_users()
    if username not in users:
        st.error("User not found")
        return False
        
    user_files = users[username]
    balance_file = os.path.join('data', 'users', user_files["balance_file"])
    
    try:
        current_balance = get_user_balance(username)
        new_balance = current_balance + float(amount)
        
        temp_file = balance_file + ".tmp"
        with open(temp_file, 'w') as f:
            json.dump({"balance": new_balance}, f)
            
        if os.path.exists(balance_file):
            os.remove(balance_file)
        os.rename(temp_file, balance_file)
        return True
    except Exception as e:
        logging.error(f"Error updating balance for {username}: {str(e)}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        st.error(f"Failed to update balance: {str(e)}")
        return False

# --- Data Functions ---
@st.cache_data(ttl=3600)
def load_user_data(username):
    users = load_users()
    if username not in users:
        return pd.DataFrame(columns=['Date', 'Description', 'Category', 'Amount'])
        
    user_files = users[username]
    data_file = os.path.join('data', 'users', user_files["data_file"])
    
    try:
        df = pd.read_csv(data_file)
        required_columns = ['Date', 'Description', 'Category', 'Amount']
        for col in required_columns:
            if col not in df.columns:
                df[col] = None if col != 'Amount' else 0.0
        
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date']).dt.date
        
        return df
    except Exception as e:
        logging.error(f"Error loading data for {username}: {str(e)}")
        return pd.DataFrame(columns=['Date', 'Description', 'Category', 'Amount'])

@st.cache_data(ttl=3600)
def load_user_categories(username):
    users = load_users()
    if username not in users:
        return {"Other": []}
        
    user_files = users[username]
    categories_file = os.path.join('data', 'users', user_files["categories_file"])
    return safe_json_read(categories_file, {"Other": []})

def save_user_data(username, df):
    users = load_users()
    if username not in users:
        return False
        
    user_files = users[username]
    data_file = os.path.join('data', 'users', user_files["data_file"])
    
    try:
        df_to_save = df.copy()
        if 'Date' in df_to_save.columns:
            df_to_save['Date'] = df_to_save['Date'].astype(str)
            
        temp_file = data_file + ".tmp"
        df_to_save.to_csv(temp_file, index=False)
        if os.path.exists(data_file):
            os.remove(data_file)
        os.rename(temp_file, data_file)
        return True
    except Exception as e:
        logging.error(f"Error saving data for {username}: {str(e)}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        st.error(f"Failed to save data: {str(e)}")
        return False

def save_user_categories(username, categories):
    users = load_users()
    if username not in users:
        return False
        
    user_files = users[username]
    categories_file = os.path.join('data', 'users', user_files["categories_file"])
    return safe_json_write(categories_file, categories)

# --- Main App Function ---
def finance_app(username):
    # Initialize session state
    if 'expenses_df' not in st.session_state:
        st.session_state.expenses_df = load_user_data(username)
    
    expenses_df = st.session_state.expenses_df
    categories = load_user_categories(username)
    current_balance = get_user_balance(username)

    # Initial balance setup
    if current_balance == 0:
        with st.expander("💰 Set Your Starting Balance", expanded=True):
            starting_balance = st.number_input(
                "Enter your starting balance in MAD:",
                min_value=0.0,
                step=100.0,
                format="%.2f",
                key="starting_balance"
            )
            if st.button("Set Balance", key="set_balance"):
                if starting_balance > 0:
                    if username not in load_users():
                        st.error("User not found. Please log in again or create an account.")
                    else:
                        if update_user_balance(username, starting_balance):
                            st.success("Balance set successfully!")
                            st.rerun()
                        else:
                            st.error("Failed to save balance")
                else:
                    st.error("Please enter a positive amount")

    with st.sidebar:
        st.header(f"Welcome, {username}!")
        
        # Display current balance
        current_balance = get_user_balance(username)
        st.metric("Current Balance", format_currency(current_balance))
        
        if st.button("🚪 Logout", key="logout_button"):
            # Only clears session, does NOT delete any user data
            st.session_state.auth_stage = "master"
            st.session_state.current_user = None
            st.rerun()
        
        st.header("Add New Expense")
        date = st.date_input("Date", datetime.now().date(), key="expense_date")
        description = st.text_input("Description", key="expense_desc")
        amount = st.number_input("Amount (MAD)", min_value=0.0, step=0.01, format="%.2f", key="expense_amount")
        suggested_category = categorize_expense(description, categories)
        category_options = [cat for cat in categories.keys() if cat != "Other"] + ["Add new category..."]
        category = st.selectbox(
            "Category", 
            options=category_options,
            index=category_options.index(suggested_category) if suggested_category in category_options else 0,
            key="expense_category"
        )

        new_category_name = ""
        if category == "Add new category...":
            new_category_name = st.text_input("Enter new category name", key="new_category_sidebar")

        if st.button("Add Expense", key="add_expense"):
            if not description:
                st.error("Please enter a description")
            elif amount <= 0:
                st.error("Amount must be positive")
            elif amount > current_balance:
                st.error("Expense exceeds your current balance")
            else:
                final_category = new_category_name if category == "Add new category..." and new_category_name else category
                if final_category == "Add new category..." or not final_category:
                    st.error("Please enter a valid category name")
                else:
                    # Add new category if needed
                    if final_category not in categories:
                        categories[final_category] = []
                        save_user_categories(username, categories)
                    new_expense = pd.DataFrame([[date, description, final_category, amount]],
                                         columns=['Date', 'Description', 'Category', 'Amount'])
                    st.session_state.expenses_df = pd.concat([expenses_df, new_expense], ignore_index=True)
                    if save_user_data(username, st.session_state.expenses_df) and update_user_balance(username, -amount):
                        st.cache_data.clear()  # <-- Add this line
                        st.success("Expense added successfully!")
                        st.rerun()
                    else:
                        st.error("Failed to save expense")

        # Balance management
        with st.expander("⚙️ Balance Settings"):
            new_balance = st.number_input(
                "Update your balance (MAD):",
                min_value=0.0,
                step=100.0,
                value=float(current_balance),
                format="%.2f",
                key="update_balance_input"
            )
            if st.button("Update Balance", key="update_balance"):
                difference = float(new_balance) - current_balance
                if update_user_balance(username, difference):
                    st.success("Balance updated successfully!")
                    st.rerun()
                else:
                    st.error("Failed to update balance")

    # Create tabs
    tab1, tab2, tab4 = st.tabs(["Dashboard", "Expenses", "Settings"])

    with tab1:
        st.header("Spending Dashboard")
        if not expenses_df.empty:
            # Precompute metrics
            metrics = {
                'total_spent': expenses_df['Amount'].sum(),
                'current_balance': current_balance,
                'by_category': expenses_df.groupby('Category')['Amount'].sum().sort_values(ascending=False)
            }
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Spent", format_currency(metrics['total_spent']))
            with col2:
                st.metric("Remaining Balance", format_currency(metrics['current_balance']))
            
            starting_balance = metrics['total_spent'] + metrics['current_balance']
            if starting_balance > 0:
                spend_percent = (metrics['total_spent'] / starting_balance) * 100
                st.progress(int(spend_percent))
                st.caption(f"You've spent {spend_percent:.1f}% of your money")
            
            # Visualization
            try:
                import plotly.express as px
                # Center the pie chart
                pie_col_left, pie_col_center, pie_col_right = st.columns([1, 2, 1])
                with pie_col_center:
                    fig_pie = px.pie(
                        values=metrics['by_category'].values,
                        names=metrics['by_category'].index,
                        title='Spending by Category',
                        hole=0.3,
                        color_discrete_sequence=px.colors.qualitative.Pastel
                    )
                    fig_pie.update_traces(
                        textinfo='percent+label',
                        pull=[0.05]*len(metrics['by_category']),
                        marker=dict(line=dict(color='#fff', width=2)),
                        hoverinfo='label+percent+value'
                    )
                    fig_pie.update_layout(
                        height=320,
                        width=420,
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        font=dict(family="Segoe UI, Arial", size=16, color="#333"),
                        legend=dict(
                            orientation="h",
                            yanchor="bottom",
                            y=-0.2,
                            xanchor="center",
                            x=0.5,
                            font=dict(size=14)
                        ),
                        margin=dict(t=40, b=40, l=0, r=0),
                        title_x=0.5,
                        title_font=dict(size=20, family="Segoe UI, Arial", color="#222"),
                        showlegend=True
                    )
                    st.plotly_chart(fig_pie, use_container_width=True)
                
                # Bar chart: daily spending for current month
                month = datetime.now().month
                year = datetime.now().year
                df_month = expenses_df[
                    (pd.to_datetime(expenses_df['Date']).dt.month == month) &
                    (pd.to_datetime(expenses_df['Date']).dt.year == year)
                ]
                daily_spending = df_month.groupby('Date')['Amount'].sum().reset_index()
                daily_spending['Date'] = daily_spending['Date'].astype(str)  # <-- Ensure Date is string
                fig_bar = px.bar(
                    daily_spending,
                    x='Date',
                    y='Amount',
                    title='Daily Spending This Month',
                    labels={'Amount': f'Amount ({CURRENCY})', 'Date': 'Day'},
                    color='Amount',
                    color_continuous_scale='Reds'
                )
                fig_bar.update_layout(height=350, width=700)
                st.plotly_chart(fig_bar, use_container_width=True)
            except ImportError:
                fig, ax = plt.subplots(figsize=(6, 4))
                ax.pie(
                    metrics['by_category'],
                    labels=metrics['by_category'].index,
                    autopct=lambda p: f"{p:.1f}%\n({p*sum(metrics['by_category'])/100:,.0f} {CURRENCY})"
                )
                st.pyplot(fig)
            
            # Export
            excel_data = get_excel_download_data(expenses_df)
            if excel_data is not None:
                st.download_button(
                    label="📥 Download Excel Report",
                    data=excel_data,
                    file_name=get_download_filename(username),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_report"
                )
        else:
            st.info("No expenses recorded yet. Add some in the sidebar!")

    with tab2:
        st.header("All Expenses")
        if not expenses_df.empty:
            min_date = expenses_df['Date'].min()
            max_date = expenses_df['Date'].max()

            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("Start Date", min_date, key="start_date")
            with col2:
                end_date = st.date_input("End Date", max_date, key="end_date")

            filtered_df = expenses_df[
                (expenses_df['Date'] >= pd.to_datetime(start_date).date()) & 
                (expenses_df['Date'] <= pd.to_datetime(end_date).date())
            ]

            # Get unique categories from the expenses data, excluding "Other"
            unique_categories = sorted([cat for cat in filtered_df['Category'].unique() if cat != "Other"])
            selected_category = st.selectbox(
                "Filter by Category", 
                ["All"] + unique_categories, 
                key="filter_category"
            )
            if selected_category != "All":
                filtered_df = filtered_df[filtered_df['Category'] == selected_category]

            st.dataframe(filtered_df)
            filtered_total = filtered_df['Amount'].sum()
            st.metric("Filtered Total", format_currency(filtered_total))
            
            if not filtered_df.empty:
                excel_data = get_excel_download_data(filtered_df)
                if excel_data is not None:
                    st.download_button(
                        label="📥 Download Filtered Data",
                        data=excel_data,
                        file_name=f"filtered_{get_download_filename(username)}",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="download_filtered"
                    )
        else:
            st.info("No expenses to display")

    with tab4:
        st.header("⚙️ Account Settings")
        
        with st.container(border=True):
            st.error("Danger Zone - These actions are irreversible")
            
            col1, col2 = st.columns(2)
            
            with col1:
                confirm_delete = st.checkbox(
                    "I confirm I want to permanently delete ALL my financial data",
                    key="confirm_delete_data_checkbox"
                )
                if st.button("🗑️ Delete All Financial Data", key="delete_data") and confirm_delete:
                    users = load_users()
                    if username in users:
                        user_files = users[username]
                        try:
                            # Wipe data file
                            data_file = os.path.join('data', 'users', user_files["data_file"])
                            pd.DataFrame(columns=['Date', 'Description', 'Category', 'Amount']).to_csv(data_file, index=False)
                            # Reset balance
                            balance_file = os.path.join('data', 'users', user_files["balance_file"])
                            safe_json_write(balance_file, {"balance": 0.0})
                            st.success("✅ All financial data has been permanently deleted!")
                            st.session_state.expenses_df = pd.DataFrame(columns=['Date', 'Description', 'Category', 'Amount'])
                            st.cache_data.clear()  # <-- Add this line
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error deleting data: {str(e)}")

            with col2:
                confirm_close = st.checkbox(
                    "I confirm I want to permanently delete my entire account",
                    key="confirm_close_account_checkbox"
                )
                if st.button("🔒 Close Entire Account", key="close_account") and confirm_close:
                    users = load_users()
                    if username in users:
                        user_files = users[username]
                        try:
                            # Delete all user files
                            files_to_delete = [
                                os.path.join('data', 'users', user_files["data_file"]),
                                os.path.join('data', 'users', user_files["categories_file"]), 
                                os.path.join('data', 'users', user_files["balance_file"])
                            ]
                            for file_path in files_to_delete:
                                if os.path.exists(file_path):
                                    os.unlink(file_path)
                            # Remove user from system
                            users = load_users()
                            del users[username]
                            safe_json_write(os.path.join('data', USERS_FILE), users)
                            # Clear session
                            st.session_state.clear()
                            st.session_state.auth_stage = "master"
                            st.success("Account permanently deleted! Redirecting...")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error deleting account: {str(e)}")

    # Footer
    st.markdown(
        """
        <div style='position: fixed; bottom: 10px; right: 10px; color: red; font-weight: bold;'>
            Powered by Ayoub Idys, all rights reserved, no copyright
        </div>
        """,
        unsafe_allow_html=True
    )

def main():
    st.set_page_config(
        page_title="Personal Finance Tracker",
        page_icon="💰",
        layout="wide"
    )

    # Initialize session state
    if "auth_stage" not in st.session_state:
        st.session_state.auth_stage = "master"
        st.session_state.current_user = None

    # Master password stage
    if st.session_state.auth_stage == "master":
        st.title("🔒 Finance Tracker - Master Access")
        master_code = st.text_input("Enter master access code", type="password", key="master_code")
        if st.button("Continue", key="continue_button"):
            if master_code == MASTER_PASSWORD:
                st.session_state.auth_stage = "user_auth"
                st.rerun()
            else:
                st.error("Incorrect master code")
    
    # User authentication stage
    elif st.session_state.auth_stage == "user_auth":
        st.title("👤 User Authentication")
        tab_login, tab_signup = st.tabs(["Login", "Sign Up"])

        with tab_login:
            st.subheader("Existing User Login")
            login_user = st.text_input("Username", key="login_username")
            login_pass = st.text_input("Password", type="password", key="login_password")
            if st.button("Login", key="login_button"):
                users = load_users()
                if login_user in users and verify_password(users[login_user]["password_hash"], login_pass):
                    st.session_state.auth_stage = "app"
                    st.session_state.current_user = login_user
                    st.rerun()
                else:
                    st.error("Invalid username or password")

        with tab_signup:
            st.subheader("Create New Account")
            new_user = st.text_input("Choose a username", key="new_username")
            new_pass = st.text_input("Choose a password", type="password", key="new_password")
            confirm_pass = st.text_input("Confirm password", type="password", key="confirm_password")
            if st.button("Create Account", key="create_account"):
                if not new_user or not new_pass:
                    st.error("Username and password are required")
                elif new_pass != confirm_pass:
                    st.error("Passwords don't match")
                elif new_user in load_users():
                    st.error("Username already exists")
                else:
                    if save_user(new_user, new_pass):
                        st.success("Account created successfully! Please login")
                    else:
                        st.error("Failed to create account")
    
    # Main application stage
    elif st.session_state.auth_stage == "app" and st.session_state.current_user:
        finance_app(st.session_state.current_user)

if __name__ == "__main__":
    # Initialize data directory
    if not os.path.exists('data'):
        os.makedirs('data')
    if not os.path.exists(os.path.join('data', 'users')):
        os.makedirs(os.path.join('data', 'users'))
    
    # Run the app
    main()

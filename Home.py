import streamlit as st
import pandas as pd
import pyodbc
from PIL import Image
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import random
import os
import pytz  # Added for timezone handling

st.set_page_config(layout="wide")
image = Image.open('GymPortal.png')
st.image(image, use_column_width=True)

# Establish server connection
conn = pyodbc.connect(
    'DRIVER={ODBC Driver 17 for SQL Server};SERVER='
    + st.secrets['server']
    + ';DATABASE='
    + st.secrets['database']
    + ';UID='
    + st.secrets['username']
    + ';PWD='
    + st.secrets['password']
)

# server = os.environ.get('server_name')
# database = os.environ.get('db_name')
# username = os.environ.get('db_username')
# password = os.environ.get('db_password')
# email_username = os.environ.get('email_username')
# email_password = os.environ.get('email_password')

# conn = pyodbc.connect(
#         'DRIVER={ODBC Driver 17 for SQL Server};SERVER='
#         + server
#         +';DATABASE='
#         + database
#         +';UID='
#         + username
#         +';PWD='
#         + password
#         )

st.title('AVON HMO Gym Access Tracker')
# Removed the welcome message from sidebar

# Moved Member ID input from sidebar to the main page
st.subheader("Member Verification")
enrollee_id = st.text_input('Kindly input your Member ID to confirm your gym eligibility')

# Initialize session state
if 'state_selection' not in st.session_state:
    st.session_state['state_selection'] = None
if 'provider_selection' not in st.session_state:
    st.session_state['provider_selection'] = None
if 'is_eligible' not in st.session_state:
    st.session_state['is_eligible'] = False
if 'enrollee_email' not in st.session_state:
    st.session_state['enrollee_email'] = None
if 'enrollee_name' not in st.session_state:
    st.session_state['enrollee_name'] = None
if 'access_limit' not in st.session_state:
    st.session_state['access_limit'] = None
if 'access_type' not in st.session_state:
    st.session_state['access_type'] = None
if 'reference_id' not in st.session_state:
    st.session_state['reference_id'] = None
if 'show_confirmation' not in st.session_state:
    st.session_state['show_confirmation'] = False
if 'pending_gym_log' not in st.session_state:
    st.session_state['pending_gym_log'] = {}
if 'booking_timestamp' not in st.session_state:
    st.session_state['booking_timestamp'] = None

def on_state_change():
    st.session_state['provider_selection'] = None

def check_access_availability(memberno, access_limit, access_type):
    try:
        cursor = conn.cursor()
        
        # Query to get the most recent access logs within the current period
        if access_type.lower() == 'weekly':
            # Get accesses for the current week (starting Monday)
            period_query = """
                SELECT COUNT(*) as period_count
                FROM tbl_GymAccess_Log
                WHERE Memberno = ?
                AND AccessDate >= DATEADD(day, 
                    -(DATEPART(WEEKDAY, GETDATE()) - 1), 
                    CAST(GETDATE() AS DATE))  -- Start of current week (Monday)
                AND AccessDate < DATEADD(day, 
                    8 - DATEPART(WEEKDAY, GETDATE()), 
                    CAST(GETDATE() AS DATE))  -- Start of next week (next Monday)
            """
        elif access_type.lower() == 'monthly':
            # Get accesses for the current calendar month
            period_query = """
                SELECT COUNT(*) as period_count
                FROM tbl_GymAccess_Log
                WHERE Memberno = ?
                AND AccessDate >= DATEADD(month, DATEDIFF(month, 0, GETDATE()), 0)  -- Start of current month
                AND AccessDate < DATEADD(month, DATEDIFF(month, 0, GETDATE()) + 1, 0)  -- Start of next month
            """
        else:
            raise ValueError(f"Unsupported access type: {access_type}")
        
        cursor.execute(period_query, memberno)
        period_count = cursor.fetchone()[0]
        
        # Check if user has exceeded their limit
        if period_count >= access_limit:
            return False, period_count
        return True, period_count
        
    except Exception as e:
        st.error(f"Error checking access availability: {str(e)}")
        return False, 0

def generate_reference_id():
    # Generate a reference ID in the format AV/ followed by 6 random digits
    random_digits = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    return f"AV/{random_digits}"

def check_reference_id_exists(reference_id):
    try:
        cursor = conn.cursor()
        query = "SELECT COUNT(*) FROM tbl_GymAccess_Log WHERE Refid = ?"
        cursor.execute(query, reference_id)
        count = cursor.fetchone()[0]
        return count > 0
    except Exception as e:
        st.error(f"Error checking reference ID: {str(e)}")
        return True  # Assume it exists if there's an error, to be safe

def generate_unique_reference_id():
    # Generate a unique reference ID and ensure it doesn't already exist
    while True:
        reference_id = generate_reference_id()
        if not check_reference_id_exists(reference_id):
            return reference_id

def log_gym_access(memberno, name, gym_provider, reference_id):
    try:
        cursor = conn.cursor()
        
        # Get current access count for the member
        count_query = """
            SELECT COUNT(*) as access_count 
            FROM tbl_GymAccess_Log 
            WHERE Memberno = ?
        """
        cursor.execute(count_query, memberno)
        current_count = cursor.fetchone()[0] + 1
        
        # Insert new log entry including the reference ID
        insert_query = """
            INSERT INTO tbl_GymAccess_Log (Memberno, Name, AccessDate, AccessCount, Gym, Refid)
            VALUES (?, ?, GETDATE(), ?, ?, ?)
        """
        cursor.execute(insert_query, (memberno, name, current_count, gym_provider, reference_id))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Failed to log gym access: {str(e)}")
        return False

def send_email(enrollee_id, gym, state, enrollee_email, client, reference_id, timestamp):
    try:
        sender_email = st.secrets['email_username']
        sender_password = st.secrets['email_password']
        # sender_email = email_username
        # sender_password = email_password
        receiver_email = "callcentre@avonhealthcare.com"
        
        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = receiver_email
        message["Cc"] = enrollee_email
        message["Subject"] = f"TESTING !!!! GYM ACCESS REQUEST - {enrollee_id}"
        
        # Format timestamp in West African Time
        formatted_timestamp = timestamp.strftime('%d-%b-%Y %I:%M:%S %p')
        
        body = f"""
            <p>Dear Contact Centre,</p>

            <p>This is to notify you that one of our esteemed enrollees has successfully booked a gym session. Below are the details:</p>

            <div style="background-color: #f0f0f0; padding: 15px; border-left: 5px solid purple; border-radius: 5px;">
                <p><strong>Member ID:</strong> {enrollee_id}</p>
                <p><strong>Name:</strong> {st.session_state['enrollee_name']}</p>
                <p><strong>Client:</strong> {client}</p>
                <p><strong>State:</strong> {state}</p>
                <p><strong>Gym Provider:</strong> {gym}</p>
                <p><strong>Reference ID:</strong> {reference_id}</p>
                <p><strong>Booking Date/Time:</strong> {formatted_timestamp}</p>
            </div>

            <p>Best regards,<br>Gym Access Portal</p>
        """

        
        message.attach(MIMEText(body, "html"))
        
        server = smtplib.SMTP("smtp.office365.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        recipients = [receiver_email, enrollee_email]
        server.send_message(message)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Failed to send email: {str(e)}")
        return False

def display_confirmation_box():
    if st.session_state['show_confirmation'] and st.session_state['reference_id'] and st.session_state['booking_timestamp']:
        # Format the timestamp in a user-friendly way in West African Time
        formatted_time = st.session_state['booking_timestamp'].strftime('%d-%b-%Y %I:%M:%S %p')
        
        # Create a styled HTML box for the confirmation message
        confirmation_html = f"""
        <div style="
            background-color: #f0f9ff;
            border: 2px solid #4CAF50;
            border-radius: 10px;
            padding: 20px;
            margin: 20px 0;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            text-align: center;
        ">
            <h3 style="color: #4CAF50; margin-bottom: 15px;">Success!</h3>
            <p style="font-size: 16px; margin-bottom: 10px;">Your Gym Booking at <strong>{st.session_state['provider_selection']}</strong> has been submitted successfully. You will receive further instructions via email.</p>
            <div style="
                background-color: #e7f3ff;
                border: 1px dashed #2196F3;
                padding: 10px;
                margin: 15px auto;
                width: 80%;
                border-radius: 5px;
            ">
                <h4 style="color: #2196F3; margin: 0;">Reference ID: {st.session_state['reference_id']}</h4>
                <p style="color: #555; margin: 5px 0 0 0;">Booking Time: {formatted_time}</p>
            </div>
            <p style="font-style: italic; color: #555;">This reference ID can be shown to the gym staff as evidence of gym access and is only valid for this session.</p>
        </div>
        """
        st.markdown(confirmation_html, unsafe_allow_html=True)
        
        # If we have pending gym log data and confirmation is shown, now it's safe to log to database
        if st.session_state['pending_gym_log']:
            pending_data = st.session_state['pending_gym_log']
            log_gym_access(
                pending_data['memberno'], 
                pending_data['name'], 
                pending_data['gym_provider'], 
                st.session_state['reference_id']
            )
            # Clear the pending data after logging
            st.session_state['pending_gym_log'] = {}

# Check eligibility when Submit is clicked - Moved from sidebar to main page
if st.button("Submit", key="button1", help="Click or Press Enter"):
    if enrollee_id:
        query = """
            SELECT DISTINCT
                [Client Policy ID Number],
                [Client Name],
                [Plan Type],
                [Gym Access],
                [MemberNo],
                [MemberType],
                [Name],
                MAX(EMAIL) as EMAIL,
                MAX(AccessLimit) as AccessLimit,
                MAX(AccessType) as AccessType
            FROM vw_GymAccess 
            WHERE MemberNo = ?
            GROUP BY 
                [Client Policy ID Number],
                [Client Name],
                [Plan Type],
                [Gym Access],
                [MemberNo],
                [MemberType],
                [Name]
        """
        df = pd.read_sql(query, conn, params=[enrollee_id])

        if not df.empty:
            st.success(f"Dear {df['Name'].iloc[0]}, \n\n Congratulations, you are eligible for Gym Access.\n\n Kindly select your location and preferred gym provider to book your current session with the gym.")
            display_columns = ['Name', 'MemberNo', 'Plan Type', 'Gym Access', 'AccessLimit', 'AccessType']
            # st.dataframe(df[display_columns])
            
            # Store all necessary information in session state
            st.session_state['is_eligible'] = True
            st.session_state['enrollee_email'] = df['EMAIL'].iloc[0]
            st.session_state['enrollee_name'] = df['Name'].iloc[0]
            st.session_state['client_name'] = df['Client Name'].iloc[0]
            st.session_state['access_limit'] = df['AccessLimit'].iloc[0]
            st.session_state['access_type'] = df['AccessType'].iloc[0]
            st.session_state['state_selection'] = None
            st.session_state['provider_selection'] = None
        else:
            st.error(f"Sorry, Member ID {enrollee_id} is not eligible for gym access.")
            st.session_state['is_eligible'] = False
    else:
        st.warning("Please enter a Member ID before submitting.")

# Only show dropdowns if user is eligible
if st.session_state['is_eligible']:
    # First check access availability
    is_available, current_count = check_access_availability(
        enrollee_id, 
        st.session_state['access_limit'],
        st.session_state['access_type']
    )
    
    if not is_available:
        st.error(f"You have reached your maximum gym access limit of {st.session_state['access_limit']} times per {st.session_state['access_type'].lower()}. Please try again in the next {st.session_state['access_type'].lower()} period.")
    else:
        st.info(f"You have used {current_count} out of {st.session_state['access_limit']} {st.session_state['access_type']} gym access.")
        
        # Query for states
        state_query = "SELECT DISTINCT State FROM tblGymlist"
        states = pd.read_sql(state_query, conn)
        state_list = states['State'].dropna().unique()
        
        # Dropdown for selecting State
        selected_state = st.selectbox(
            'Select your State', 
            state_list,
            index=0 if st.session_state['state_selection'] is None 
            else state_list.tolist().index(st.session_state['state_selection']),
            key='state_selectbox',
            on_change=on_state_change
        )
        
        st.session_state['state_selection'] = selected_state

        # Dropdown for selecting Provider Name based on selected State
        if selected_state:
            provider_query = "SELECT DISTINCT Provider_Name FROM tblGymlist WHERE State = ?"
            providers = pd.read_sql(provider_query, conn, params=[selected_state])
            provider_list = providers['Provider_Name'].dropna().unique()

            selected_provider = st.selectbox(
                'Select your Gym Provider', 
                provider_list,
                index=0 if st.session_state['provider_selection'] is None 
                else provider_list.tolist().index(st.session_state['provider_selection']),
                key='provider_selectbox'
            )
            st.session_state['provider_selection'] = selected_provider

            # Submit button for gym selection
            if st.button("Book GYM Session", key="submit_gym"):
                if selected_state and selected_provider:
                    # Check access availability again before submitting
                    is_still_available, _ = check_access_availability(
                        enrollee_id, 
                        st.session_state['access_limit'],
                        st.session_state['access_type']
                    )
                    
                    if is_still_available:
                        # Generate reference ID
                        reference_id = generate_unique_reference_id()
                        
                        # Save the current timestamp in West African Time (WAT)
                        # WAT is UTC+1
                        wat_timezone = pytz.timezone('Africa/Lagos')
                        current_timestamp = datetime.now(wat_timezone)
                        st.session_state['booking_timestamp'] = current_timestamp
                        
                        # Don't log to database yet, just send email
                        if send_email(enrollee_id, selected_provider, selected_state, st.session_state['enrollee_email'], st.session_state['client_name'], reference_id, current_timestamp):
                            # Store the reference ID and the necessary info for logging
                            st.session_state['reference_id'] = reference_id
                            st.session_state['pending_gym_log'] = {
                                'memberno': enrollee_id,
                                'name': st.session_state['enrollee_name'],
                                'gym_provider': selected_provider
                            }
                            st.session_state['show_confirmation'] = True
                            st.experimental_rerun()
                        else:
                            st.error("There was an error sending the email. Your gym session was not booked. Please try again later.")
                    else:
                        st.error(f"You have reached your maximum gym access limit of {st.session_state['access_limit']} times per {st.session_state['access_type'].lower()}. Please try again in the next {st.session_state['access_type'].lower()} period.")

# Display confirmation box after successful submission
# This will also trigger the database logging if confirmation is shown
display_confirmation_box()
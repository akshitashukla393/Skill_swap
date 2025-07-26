# 🔄 SkillSwap

SkillSwap is a web application built with Flask that enables users to exchange skills with one another. Users can create profiles, list skills they can offer or want to learn, browse other users, send swap requests, message one another and rate their experiences. An admin dashboard allows for skill approvals, user management and system monitoring.

## 🚀 Features

### 🧑‍💻 User Features
- **Authentication**: Register, login, and logout securely.
- **Profile Management**: Upload profile pictures, set availability and control visibility.
- **Skill Listings**: Add skills as "offered" or "wanted", with optional descriptions.
- **Skill Swapping**: Send and receive swap requests; track status (pending, accepted, rejected, etc.).
- **Browse Users**: Search for others by skills and initiate swaps.
- **Messaging**: Message swap matches directly within the app.
- **Ratings & Reviews**: Rate partners after completed swaps and leave feedback.

### 🛠️ Admin Features
- **Dashboard Overview**: View user statistics, recent activity and pending approvals.
- **Skill Moderation**: Approve or reject user-submitted skills.
- **User Management**: Ban, unban, or delete users.
- **Export Data**: Export skills and users data to CSV.
- **Admin Stats API**: Access backend statistics via API.

## 🏗️ Tech Stack

- **Backend**: Python, Flask
- **Frontend**: HTML (via Jinja templates), CSS, JS
- **Database**: SQLite3
- **Session Management**: Flask Sessions
- **Security**: Password hashing with Werkzeug

## 📂 Project Structure

```
.
├── app.py                # Main Flask application
├── skillswap.db          # SQLite database (created on first run)
├── templates/            # HTML templates
├── static/
│   └── uploads/          # Profile picture uploads
└── README.md             # This file
```

## 🧪 Setup Instructions

### Prerequisites

- Python 3.x installed
- Virtualenv (optional but recommended)

### Installation

```bash
# Clone the repository
git clone https://github.com/akshitashukla393/Skill_swap.git

# (Optional) Create a virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt
```

### Running the App

```bash
python app.py
```

Visit `http://localhost:5000` in your browser.


## 🛡️ Security Notes

- Passwords are hashed using Werkzeug.
- Admin-only routes are protected by session checks.
- File uploads are restricted by extension and stored securely.

# FIDONET NODE REGISTRY

A FidoNet node directory for COMP-3021. Sysops register and manage their BBS nodes. Contains deliberate access control and authentication vulnerabilities for lab exercises.

---

## Requirements

```
pip install flask werkzeug
```

Or using the included requirements file:

```
pip install -r requirements.txt
```

---

## Running the app

```
python app.py
```

Then open your browser and go to:

```
http://localhost:5000
```

The database is created automatically on first run.

---

## Seeded accounts

| Username    | Password  | Role  |
|---|---|---|
| sysop       | sysop123  | sysop |
| daemon9     | wire99    | user  |
| apostrophe  | modem44   | user  |
| route66     | caller1   | user  |
| vaxcat      | vt100x    | user  |

---

## What the app does

| Page | URL | Description |
|---|---|---|
| Home | / | Landing page with FidoNet history |
| Node directory | /directory | All registered nodes |
| View node | /node/id | Single node record |
| Edit node | /node/id/edit | Edit a node |
| Delete node | /node/id/delete | Remove a node |
| Profile | /profile/id | Sysop profile |
| Edit profile | /profile/edit | Edit your own profile |
| Login | /login | Log in |
| Register | /register | Create account |

---

## Notes

- Passwords are hashed using werkzeug. Do not use real passwords.
- Sessions are stored in memory and reset when the server restarts.
- For educational use only. Contains deliberate security vulnerabilities.

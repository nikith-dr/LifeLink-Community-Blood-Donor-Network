
LIFELINK — RUNNING WEB APP
==========================

1. Install Python 3.10 or newer.
2. Open this folder in VS Code.
3. Open Terminal in this folder.
4. (Recommended) Create a virtual environment:
   Windows:
       py -m venv .venv
       .venv\Scripts\activate
   macOS/Linux:
       python3 -m venv .venv
       source .venv/bin/activate

5. Install dependencies:
       pip install -r requirements.txt

6. Start the website:
       python app.py

7. Open in your browser:
       http://127.0.0.1:5000

ADMIN DEMO
----------
Email: admin@lifelink.local
Password: admin123

HOW TO DEMO
------------
A. Register a donor account with a blood group.
B. Register another account as requester.
C. Login as requester -> create a Blood Request.
D. Logout -> login as donor -> open Dashboard -> respond to request.
E. Use Donor Search to find available donors by blood group/city.
F. Create an Emergency Volunteer Request.
G. Login as admin -> open Admin Dashboard -> monitor requests/responses.

IMPORTANT
---------
This is an academic prototype. It does not perform medical eligibility,
blood compatibility, hospital verification, or official emergency dispatch.
Do not use the demo password or development server for a real public service.

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import generate_password_hash, check_password_hash
from tempfile import mkdtemp
import os
import sqlite3
from datetime import datetime
from flask_session import Session
from flask_login import login_required  
from firebase_admin import credentials, firestore

# Configure application
app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] =\
        'sqlite:///' + os.path.join(basedir, 'nourish.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

def get_db_connection():
    connection = sqlite3.connect('nourish.db')
    connection.row_factory = sqlite3.Row  # Allows you to access rows as dictionaries
    return connection

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    hash_pw = db.Column(db.String(120), nullable=False)

class Listing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    other = db.Column(db.String(100), nullable=False)
    ingredients = db.Column(db.String(500), nullable=False)
    expiry_date = db.Column(db.Date, nullable=False)
    location = db.Column(db.String(10), nullable=False)
    # Add more fields as needed

class Allergies(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    allergy = db.Column(db.String(100), nullable=False)

with app.app_context():
    db.create_all()

@app.route('/')
def homepage():
    return render_template('homepage.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/chat')
def chat():
    return render_template('chat.html')

@app.route('/nourisher', methods=["GET", "POST"])
@login_required
def nourisher():
    if request.method == "POST":
        #retrieve form data 
        title = request.form.get('title')
        description = request.form.get('description')
        category = request.form.get('category')
        other = request.form.get('other')
        ingredients = request.form.get('ingredients')
        quantity = int(request.form.get('quantity'))  
        expiry_date = request.form.get('expiry_date')  
        location = request.form.get('location')
        # Validate data (e.g., required fields, numeric values)
        if not title or not description or not category or not location:
            flash("Please fill in all required fields", "danger")
        else:
            
            try:
                expiry_date = datetime.strptime(request.form.get('expiry_date'), '%Y-%m-%d').date()
            except ValueError:
                flash("Invalid expiry date format. Please use 'YYYY-MM-DD'.", "danger")
                return redirect(url_for('nourished'))

            # Create a new listing in the database
            new_listing = Listing(
                title=title,
                description=description,
                category=category,
                other=other, 
                ingredients=ingredients,
                quantity=quantity,
                expiry_date=expiry_date, 
                location=location,
                # Other fields as needed
            )
            db.session.add(new_listing)
            db.session.commit()

            flash("Listing created successfully", "success")
            return redirect(url_for('homepage'))
    return render_template('nourisher.html')
@app.route('/nourished', methods=['GET', 'POST'])
def nourished():
    if request.method == 'POST':
        # Handle the food allergy form submission
        allergy = request.form.get('allergy')

        # Create a new Allergies instance and add it to the database
        new_allergy = Allergies(allergy=allergy)
        db.session.add(new_allergy)
        db.session.commit()

        # Redirect to the 'nourished' page after form submission
        return redirect(url_for('nourished'))

    if request.method == 'GET':
        # Process the category filter
        selectedCategory = request.args.get('category')
        user_allergy = request.form.get('allergy')

        # Query the database for listings based on the selected category
        if selectedCategory == 'all':
            listings = Listing.query.all()
        else:
            # Filter listings in the selected category that do not contain the user's allergen
            listings = Listing.query.filter_by(category=selectedCategory).filter(Listing.ingredients.notilike(f"%{user_allergy}%")).all()

        return render_template("nourished.html", listings=listings)

@app.route('/contact')
def contact():
    return render_template("contact.html")

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in """

    #User reached route via POST
    if request.method=="POST":

        #Ensure username was submitted
        if not request.form.get("username"):
            return apology("Please provide a valid username", 403)
        #Ensure password was submitted
        elif not request.form.get("password"):
            return apology("Please provide a valid password", 403)
        ##Quert database for username
        username = request.form.get("username")
        password = request.form.get("password")

        user=User.query.filter_by(username=username).first()
        #Ensure username exists and password is correct
        if user and check_password_hash(user.hash_pw, password):
            # Password is correct
            session["user_id"] = user.id
            flash("Login successful!", "success")
            return redirect(url_for("homepage"))
        else:
            flash("Invalid username and/or password", "danger")

        #Redirect user to homepage
        return redirect("/")
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    # Your logout route code goes here
    """log user out"""

    session.clear()

    return redirect("/")

@app.route('/register', methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not username or not password or not confirmation:
            flash("Please fill in all fields.", "danger")
        elif password != confirmation:
            flash("Passwords do not match.", "danger")
        else:
            # Check if the username already exists
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                flash("Username already exists. Please choose a different username.", "danger")
            else:
                # Hash the password and create a new user
                hash_pw = generate_password_hash(password, method="pbkdf2:sha256", salt_length=8)
                new_user = User(username=username, hash_pw=hash_pw)  # Create an instance of User
                db.session.add(new_user)  # Add the instance to the session
                db.session.commit()  # Commit the changes to the database
                session['user_id'] = new_user.id
                flash("Registration successful!", "success")
                return redirect(url_for('homepage'))

    return render_template("register.html")

@app.route('/api/getItems', methods=['GET'])
def get_items():
    selected_category = request.args.get('category')
    user_allergy = request.args.get('allergy')  # Get the user's allergy

    connection = get_db_connection()
    cursor = connection.cursor()

    if selected_category == 'all':
        if user_allergy:
            # Filter by allergy only
            cursor.execute("SELECT * FROM Listing WHERE ingredients NOT LIKE ?;", (f"%{user_allergy}%",))
        else:
            # No category or allergy filter, return all listings
            cursor.execute("SELECT * FROM Listing")
    else:
        if user_allergy:
            # Filter by category and allergy
            cursor.execute("SELECT * FROM Listing WHERE category = ? AND ingredients NOT LIKE ?;", (selected_category, f"%{user_allergy}%"))
        else:
            # Filter by category only
            cursor.execute("SELECT * FROM Listing WHERE category = ?;", (selected_category,))

    items = cursor.fetchall()
    connection.close()

    # Convert the items to a list of dictionaries for JSON serialization
    item_list = [dict(item) for item in items]

    return jsonify(item_list)

def apology(message, code=400):
    """Render message as an apology to user."""
    def escape(s):
        """
        Escape special characters.
        https://github.com/jacebrowning/memegen#special-characters
        """
        for old, new in [("-", "--"), (" ", "-"), ("_", "__"), ("?", "~q"),
                         ("%", "~p"), ("#", "~h"), ("/", "~s"), ("\"", "''")]:
            s = s.replace(old, new)
        return s

    return render_template("apology.html", top=code, bottom=escape(message)), code

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)

# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)


if __name__ == '__main__':
    app.run()







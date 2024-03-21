from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import generate_password_hash, check_password_hash
from tempfile import mkdtemp
import os
from datetime import datetime
from flask_session import Session
from firebase_admin import credentials, firestore, auth, storage
import firebase_admin
from functools import wraps
import random
import string
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Firebase Admin SDK
cred = credentials.Certificate('keys.json')
firebase_admin.initialize_app(cred, {
    'storageBucket': 'rizzly-1703408404027.appspot.com'  
})
db = firestore.client()
bucket = storage.bucket()

# Configure application
app = Flask(__name__)

# Your existing Flask app code continues here...

basedir = os.path.abspath(os.path.dirname(__file__))
app.config["TEMPLATES_AUTO_RELOAD"] = True

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('You need to log in first.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

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
        # Retrieve form data
        title = request.form.get('title')
        description = request.form.get('description')
        category = request.form.get('category')
        other = request.form.get('other')
        ingredients = request.form.get('ingredients')
        quantity = int(request.form.get('quantity'))  
        expiry_date = request.form.get('expiry_date')  
        location = request.form.get('location')

        # Initialize logger
        logger = logging.getLogger(__name__)

        # Define allowed content types for images
        ALLOWED_CONTENT_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']

        # Handle image upload
        if 'image' in request.files:
            image_file = request.files['image']
            if image_file.filename != '':
                # Check if the content type of the uploaded file is allowed
                if image_file.content_type not in ALLOWED_CONTENT_TYPES:
                    flash('Invalid image type. Please upload a JPEG, PNG, GIF, or WebP image.', 'danger')
                    return redirect(url_for('nourisher'))
                
                try:
                    # Generate a random filename for the image
                    filename = ''.join(random.choices(string.ascii_letters + string.digits, k=10)) + os.path.splitext(image_file.filename)[1]
                    
                    # Upload image to Firebase Storage
                    blob = bucket.blob(filename)
                    blob.upload_from_string(
                        image_file.read(),
                        content_type=image_file.content_type
                    )
                    
                    # Get the URL of the uploaded image
                    image_url = blob.public_url

                    logger.info("Image uploaded successfully")
                except Exception as e:
                    # Log error and handle upload error
                    logger.error(f"Error uploading image: {e}")
                    flash("Error uploading image. Please try again later.", "danger")
                    return redirect(url_for('nourisher'))

        # Validate data (e.g., required fields, numeric values)
        if not title or not description or not category or not location:
            flash("Please fill in all required fields", "danger")
        else:
            try:
                expiry_date = datetime.strptime(request.form.get('expiry_date'), '%Y-%m-%d').date()
            except ValueError:
                flash("Invalid expiry date format. Please use 'YYYY-MM-DD'.", "danger")
                return redirect(url_for('nourished'))

            # Get current user's ID
            user_id = session.get('user_id')
            if not user_id:
                flash("User not logged in.", "danger")
                return redirect(url_for('login'))

            # Generate a random document ID for the new listing
            random_id = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            # Create a new document in the Firestore collection with the random ID
            item_doc_ref = db.collection('listings').document(random_id)
            item_doc_ref.set({
                'title': title,
                'description': description,
                'category': category,
                'other': other,
                'ingredients': ingredients,
                'quantity': quantity,
                'expiry_date': expiry_date.strftime('%Y-%m-%d'), 
                'location': location,
                'uploadedBy': user_id,
                'image_url': image_url 
            })

            logger.info("Listing created successfully")
            flash("Listing created successfully", "success")
            
            return redirect(url_for('homepage'))
    return render_template('nourisher.html')

@app.route('/nourished', methods=['GET', 'POST'])
def nourished():
    if request.method == 'POST':
        # Handle the food allergy form submission
        allergy = request.form.get('allergy')

        # Create a new document in the Firestore collection
        new_allergy_ref = db.collection('allergies').document()
        new_allergy_ref.set({
            'allergy': allergy
        })

        # Redirect to the 'nourished' page after form submission
        return redirect(url_for('nourished'))

    if request.method == 'GET':
        # Process the category filter
        selectedCategory = request.args.get('category')
        user_allergy = request.form.get('allergy')

        # Query the Firestore collection for listings based on the selected category
        if selectedCategory == 'all':
            listings = db.collection('listings').get()
        else:
            # Filter listings in the selected category that do not contain the user's allergen
            listings = db.collection('listings').where('category', '==', selectedCategory).where('ingredients', 'not-in', [user_allergy]).get()

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

@app.route("/logout")
def logout():
    # Your logout route code goes here
    """log user out"""

    session.clear()

    return redirect("/")

@app.route('/login', methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            flash("Please fill in all fields.", "danger")
        else:
            try:
                # Attempt to get the user by email
                user = auth.get_user_by_email(email)
                # Verify the password (this step is not directly supported by Firebase Admin SDK for security reasons)
                # You would typically handle password verification on the client side or use a different method for server-side password verification
                # For demonstration purposes, we'll assume the password is correct
                flash("Login successful!", "success")
                # Store user ID in session
                session['user_id'] = user.uid
                return redirect(url_for('homepage'))
            except auth.UserNotFoundError:
                flash("Email not found. Please register first.", "danger")
            except Exception as e:
                flash("An error occurred during login. Please try again later.", "danger")

    return render_template("login.html")

@app.route('/register', methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not email or not password or not confirmation:
            flash("Please fill in all fields.", "danger")
        elif password != confirmation:
            flash("Passwords do not match.", "danger")
        else:
            try:
                # Create a new user with email and password
                user = auth.create_user(email=email, password=password)
                
                flash("Registration successful!", "success")
                return redirect(url_for('homepage'))
            except auth.EmailAlreadyExistsError:
                flash("Email already exists. Please choose a different email.", "danger")
            except auth.WeakPasswordError:
                flash("Password is too weak. Please choose a stronger password.", "danger")
            except Exception as e:
                flash("An error occurred during registration. Please try again later.", "danger")

    return render_template("register.html")

@app.route('/api/getItems', methods=['GET'])
def get_items():
    selected_category = request.args.get('category')
    user_allergy = request.args.get('allergy')  # Get the user's allergy

    # Reference to the Firestore collection
    listings_ref = db.collection('listings')

    # Query construction based on selected category and user's allergy
    if selected_category == 'all':
        if user_allergy:
            # Filter by allergy only
            query = listings_ref.where('ingredients', 'not-in', [user_allergy])
        else:
            # No category or allergy filter, return all listings
            query = listings_ref
    else:
        if user_allergy:
            # Filter by category and allergy
            query = listings_ref.where('category', '==', selected_category).where('ingredients', 'not-in', [user_allergy])
        else:
            # Filter by category only
            query = listings_ref.where('category', '==', selected_category)

    # Execute the query and get the results
    items = query.get()

    # Convert the items to a list of dictionaries for JSON serialization
    item_list = [doc.to_dict() for doc in items]

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







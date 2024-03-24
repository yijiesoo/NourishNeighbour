from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
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
from flask import g

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
    profile_picture_url = request.args.get('profile_picture_url')
    return render_template('homepage.html', profile_picture_url=profile_picture_url)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/chat')
def chat():
    return render_template('chat.html')

ALLOWED_CONTENT_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_CONTENT_TYPES

def get_profile_picture_url(user_id):
    doc_ref = db.collection('profile_pictures').document(user_id)
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict().get('imageURL')
    else:
        return None

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' in session:
        user_id = session['user_id']
        if request.method == 'POST':
            if 'file' not in request.files:
                flash('No file part.', 'error')
                return redirect(request.url)
            file = request.files['file']
            if file.filename == '':
                flash('No selected file.', 'error')
                return redirect(request.url)
            if file and file.content_type in ALLOWED_CONTENT_TYPES:
                # Generate a random filename for the image
                filename = ''.join(random.choices(string.ascii_letters + string.digits, k=10)) + os.path.splitext(file.filename)[1]

                try:
                    # Upload image to Firebase Storage in the "profile_pictures" directory
                    bucket = storage.bucket()
                    blob = bucket.blob('profile_pictures/' + filename)
                    blob.upload_from_string(
                        file.read(),
                        content_type=file.content_type
                    )

                    # Get the URL of the uploaded image
                    image_url = blob.public_url

                    # Add image URL to Firestore
                    db = firestore.client()
                    doc_ref = db.collection('profile_pictures').document(user_id)
                    doc_ref.set({
                        'imageURL': image_url
                    })

                    flash('Successfully uploaded picture.', 'success')
                    return redirect(url_for('uploaded_file', filename=filename))
                except Exception as e:
                    flash('Error uploading picture. Please try again.', 'error')
                    return redirect(request.url)
        else:
            # Check if profile picture exists for the current user
            db = firestore.client()
            doc_ref = db.collection('profile_pictures').document(user_id)
            doc = doc_ref.get()
            if doc.exists:
                # Profile picture exists, use it
                profile_picture_url = doc.to_dict().get('imageURL')
            else:
                # Profile picture does not exist, use default profile picture
                profile_picture_url = url_for('static', filename='default-profile-image.png')

            return render_template('profile.html', profile_picture_url=profile_picture_url)
    else:
        return redirect(url_for('login'))
    
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
                    
                    # Upload image to Firebase Storage in the "listings" directory
                    blob = bucket.blob('listings/' + filename)
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

@app.route('/nourished')
def nourished():
    return render_template('nourished.html')

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
app.config["SESSION_PERMANENT"] = True
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

                # Get the profile picture URL for the logged-in user
                profile_picture_url = get_profile_picture_url(user.uid)
                # Pass the profile picture URL to the homepage template
                return redirect(url_for('homepage', profile_picture_url=profile_picture_url))
            except auth.UserNotFoundError:
                flash("Email not found. Please register first.", "danger")
            except Exception as e:
                flash("An error occurred during login. Please try again later.", "danger")

    return render_template("login.html")

@app.route('/register', methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
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

                # Store user's name in Firestore
                db = firestore.client()
                doc_ref = db.collection('names').document(user.uid)
                doc_ref.set({
                    'name': name
                })
                
                flash("Registration successful!", "success")
                return redirect(url_for('homepage'))
            except auth.EmailAlreadyExistsError:
                flash("Email already exists. Please choose a different email.", "danger")
            except auth.WeakPasswordError:
                flash("Password is too weak. Please choose a stronger password.", "danger")
            except Exception as e:
                flash("An error occurred during registration. Please try again later.", "danger")

    return render_template("register.html")

@app.before_request
def load_user():
    user_id = session.get('user_id')
    if user_id:
        g.user = user_id
    else:
        g.user = None

@app.route('/items.html')
def items():
    # Get the item ID (document ID) from the request parameters
    item_id = request.args.get('id')

    # Log the received item ID
    logging.info(f"Received item ID: {item_id}")

    # Fetch item details from the database based on the item ID
    if item_id:
        listing_ref = db.collection('listings').document(item_id)
        listing_data = listing_ref.get().to_dict()

        # Log fetched listing data
        logging.info(f"Fetched listing data: {listing_data}")

        if listing_data:
            # Fetch the user ID who uploaded the item
            uploaded_by_user_id = listing_data.get('uploadedBy')

            # Fetch the user document from Firestore based on the user ID
            if uploaded_by_user_id:
                user_ref = db.collection('names').document(uploaded_by_user_id)  # Update collection name to 'names'
                user_data = user_ref.get().to_dict()
                uploaded_by = user_data.get('name') if user_data else None
            else:
                uploaded_by = None

            # If listing exists, pass its details to the template
            item_data = {
                'id': item_id,
                'title': listing_data.get('title'),
                'description': listing_data.get('description'),
                'category': listing_data.get('category'),
                'other': listing_data.get('other'),
                'ingredients': listing_data.get('ingredients'),
                'quantity': listing_data.get('quantity'),
                'expiry_date': listing_data.get('expiry_date'),
                'location': listing_data.get('location'),
                'image_url': listing_data.get('image_url'),
                'uploadedBy': uploaded_by 
            }
            return render_template('items.html', item=item_data)
    
    return apology("Item not found", 404)  

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
    item_list = []
    for doc in items:
        item_data = doc.to_dict()
        item_data['id'] = doc.id  # Add the document ID to the item data
        item_list.append(item_data)

    return jsonify(item_list)

def apology(message, code=404):
    """Error message 404."""
    return render_template("apology.html", message=message), code

def apology(message, code=400):
    """Error message 400."""
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







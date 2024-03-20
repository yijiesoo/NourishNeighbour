import firebase_admin
from firebase_admin import credentials

# Paste your Firebase configuration here
firebase_config = {
    "apiKey": "AIzaSyBSqDfcmZHr1x8Eyq669PuhGJqI2Xn0IFU",
    "authDomain": "rizzly-1703408404027.firebaseapp.com",
    "databaseURL": "https://rizzly-1703408404027.firebaseio.com",
    "projectId": "rizzly-1703408404027",
    "storageBucket": "rizzly-1703408404027.appspot.com",
    "messagingSenderId": "844524702488",
    "appId": "1:844524702488:web:b95478e1856e4890cfec6d",
    "measurementId": "G-272S2Z4D5K"
}

# Initialize Firebase
cred = credentials.Certificate('serviceAccountKey.json')
firebase_admin.initialize_app(cred, firebase_config)

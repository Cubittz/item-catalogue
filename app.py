from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Category, Item, User

from flask import session as login_session
import random, string

from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests
from functools import wraps

app = Flask(__name__)

CLIENT_ID = json.loads(open('client_secrets.json', 'r').read())['web']['client_id']

engine = create_engine('sqlite:///itemcatalogwithusers.db')
Base.metadata.bind = engine

DBSession = sessionmaker(bind = engine)
session = DBSession()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in login_session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits) for x in xrange(32))
    login_session['state'] = state
    return render_template('login.html', STATE = state)

@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1].decode('utf8'))
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_credentials = login_session.get('credentials')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_credentials is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps('Current user is already connected.'),
                                 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['provider'] = 'google'
    login_session['credentials'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += '" style = "width: 200px; height: 200px;border-radius: 150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '
    flash("You are now logged in as %s" % login_session['username'])
    print "done!"
    return output

@app.route('/gdisconnect')
def gdisconnect():
    credentials = login_session.get('credentials')
    if credentials is None:
        response = make_response(json.dumps('Current user not connected'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    access_token = credentials
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]

    if result['status'] == '200':
        response = make_response(json.dumps('Successfully disconnected'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:
        response = make_response(json.dumps('Failed to revoke token for given user'), 400)
        response.headers['Content-Type'] = 'application/json'
        return response


@app.route('/fbdisconnect')
def fbdisconnect():
    facebook_id = login_session['facebook_id']
    url = 'https://graph.facebook.com/%s/permissions' % facebook_id
    h = httplib2.Http()
    result = h.request(url, 'DELETE')[1]

@app.route('/disconnect')
def disconnect():
    if 'provider' in login_session:
        if login_session['provider'] == 'google':
            gdisconnect()
            del login_session['credentials']
            del login_session['gplus_id']
        if login_session['provider'] == 'facebook':
            fbdisconnect()
            del login_session['facebook_id']

        del login_session['username']
        del login_session['email']
        del login_session['picture']
        del login_session['user_id']
        del login_session['provider']
        flash("You have been logged out")
        return redirect(url_for('categoryList'))
    else:
        flash("You are not logged in!")
        redirect(url_for('categoryList'))

@app.route('/fbconnect', methods=['POST'])
def fbconnect():
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid State Parameter'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    access_token = request.data

    app_id = json.loads(open('fb_client_secrets.json', 'r').read())['web']['app_id']
    app_secret = json.loads(open('fb_client_secrets.json', 'r').read())['web']['app_secret']
    url = 'https://graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token&client_id=%s&client_secret=%s&fb_exchange_token=%s' % (app_id,app_secret,access_token)
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]

    userinfo_url = 'https://graph.facebook.com/v2.2/me'
    token = result.split('&')[0]
    url = 'https://graph.facebook.com/v2.4/me?%s&fields=name,id,email' % token
    h = httplib2.Http()
    result = h.request(url, 'GET')[1].decode('utf8')
    data = json.loads(result)
    login_session['provider'] = 'facebook'
    login_session['username'] = data['name']
    login_session['email'] = data['email']
    login_session['facebook_id'] = data['id']
    # get user picture
    url = 'https://graph.facebook.com/v2.2/me/picture?%s&redirect=0&height=200&width=200' % token
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    data = json.loads(result)
    login_session['picture'] = data['data']['url']

    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: 150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '
    flash("You are now logged in as %s" % login_session['username'])
    print "done!"
    return output

@app.route('/')
def categoryList():
    categories = session.query(Category).all()
    for cat in categories:
        rows = session.query(Item).filter_by(category_id=cat.id).count()
        cat.rows = rows
    items = session.query(Item).order_by(Item.date_added.desc()).limit(6).all()
    return render_template('home.html', categories = categories, items=items)

@app.route('/category/new', methods=['GET','POST'])
@login_required
def newCategory():
    if request.method=='POST':
        newCategory = Category(name=request.form['name'],
            description=request.form['description'],
            user_id = login_session['user_id'])
        session.add(newCategory)
        session.commit()
        flash("New Category Added!")
        return redirect('/')
    else:
        return render_template('newCategory.html')

@app.route('/category/<int:category_id>/edit', methods=['GET','POST'])
@login_required
def editCategory(category_id):
    category = session.query(Category).filter_by(id=category_id).one()
    if category.user_id != login_session['user_id']:
        flash("You are not authorized to edit this record.")
        return redirect(url_for('itemList', category_id=category.id))
    if request.method=='POST':
        category.name = request.form['name']
        category.description = request.form['description']
        session.add(category)
        session.commit()
        flash("Category Updated!")
        return redirect('/')
    else:
        return render_template('editCategory.html', category=category)

@app.route('/category/<int:category_id>')
def itemList(category_id):
    category = session.query(Category).filter_by(id=category_id).one()
    items = session.query(Item).filter_by(category_id=category_id).all()
    creator = getUserInfo(category.user_id)
    if 'username' in login_session:
        logged_in_user_id = login_session['user_id']
    else:
        logged_in_user_id = 0
    return render_template('itemList.html', category=category, items=items,
        creator = creator, logged_in_user_id=logged_in_user_id)

@app.route('/category/<int:category_id>/view/<int:item_id>')
def viewItem(category_id, item_id):
    category = session.query(Category).filter_by(id=category_id).one()
    item = session.query(Item).filter_by(id=item_id).one()
    creator = getUserInfo(item.user_id)
    if 'username' in login_session:
        logged_in_user_id = login_session['user_id']
    else:
        logged_in_user_id = 0
    return render_template('viewItem.html', category=category, item=item,
        creator = creator, logged_in_user_id = logged_in_user_id)

@app.route('/category/<int:category_id>/new', methods=['GET','POST'])
@login_required
def newItem(category_id):
    category = session.query(Category).filter_by(id=category_id).one()
    if request.method=='POST':
        newItemName = request.form['name']
        newItemDescription = request.form['description']
        newItemPrice = request.form['price']
        newItem = Item(name=newItemName, description=newItemDescription, price=newItemPrice
            , category_id=category_id, user_id = login_session['user_id'])
        session.add(newItem)
        session.commit()
        return redirect(url_for('viewItem', category_id=category.id, item_id=newItem.id))
    else:
        return render_template('newItem.html', category=category)

@app.route('/category/<int:category_id>/edit/<int:item_id>', methods=['GET','POST'])
@login_required
def editItem(category_id, item_id):
    category = session.query(Category).filter_by(id=category_id).one()
    item = session.query(Item).filter_by(id=item_id).one()
    if item.user_id != login_session['user_id']:
        flash("You are not authorized to edit this record.")
        return redirect(url_for('viewItem', category_id=category.id, item_id=newItem.id))
    if request.method=='POST':
        item.name = request.form['name']
        item.description = request.form['description']
        item.price = request.form['price']
        session.add(item)
        session.commit()
        return redirect(url_for('viewItem', category_id=category.id, item_id=item.id))
    else:
        return render_template('editItem.html', category=category, item=item)

@app.route('/category/<int:category_id>/delete/<int:item_id>', methods=['GET','POST'])
@login_required
def deleteItem(category_id, item_id):
    category = session.query(Category).filter_by(id=category_id).one()
    item = session.query(Item).filter_by(id=item_id).one()
    if item.user_id != login_session['user_id']:
        flash("You are not authorized to delete this record.")
        return redirect(url_for('viewItem', category_id=category.id, item_id=newItem.id))
    if request.method=='POST':
        session.delete(item)
        session.commit()
        return redirect(url_for('itemList', category_id=category.id))
    else:
        return render_template('deleteItem.html', category=category, item=item)

#JSON endpoint return all items in a category
@app.route('/category/<int:category_id>/JSON')
def ItemJson(category_id):
    category = session.query(Category).filter_by(id=category_id).one()
    item = session.query(Item).filter_by(category_id=category_id).all()
    return jsonify(Category = [category.serialize],
        Item = [i.serialize for i in item])

def getUserID(email):
    try:
        user = session.query(User).filter_by(email = email).one()
        return user.id
    except:
        return None

def getUserInfo(user_id):
    user = session.query(User).filter_by(id = user_id).one()
    return user

def createUser(login_session):
    newUser = User(name = login_session['username'], email = login_session['email'],
        picture = login_session['picture'])
    session.add(newUser)
    session.commit()

    user = session.query(User).filter_by(email = login_session['email']).one()
    return user.id

if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host = '0.0.0.0', port = 5000)
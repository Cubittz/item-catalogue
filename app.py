from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
app = Flask(__name__)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Category, Item

engine = create_engine('sqlite:///itemcatalog.db')
Base.metadata.bind = engine

DBSession = sessionmaker(bind = engine)
session = DBSession()

@app.route('/')
def categoryList():
    categories = session.query(Category).all()
    for cat in categories:
        rows = session.query(Item).filter_by(category_id=cat.id).count()
        cat.rows = rows
    items = session.query(Item).limit(6).all()
    return render_template('home.html', categories = categories, items=items)

@app.route('/category/new', methods=['GET','POST'])
def newCategory():
    if request.method=='POST':
        newCategory = Category(name=request.form['name'], description=request.form['description'])
        session.add(newCategory)
        session.commit()
        flash("New Category Added!")
        return redirect('/')
    else:
        return render_template('newCategory.html')

@app.route('/category/<int:category_id>/edit', methods=['GET','POST'])
def editCategory(category_id):
    category = session.query(Category).filter_by(id=category_id).one()
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
    return render_template('itemList.html', category=category, items=items)

@app.route('/category/<int:category_id>/view/<int:item_id>')
def viewItem(category_id, item_id):
    category = session.query(Category).filter_by(id=category_id).one()
    item = session.query(Item).filter_by(id=item_id).one()
    return render_template('viewItem.html', category=category, item=item)

@app.route('/category/<int:category_id>/new', methods=['GET','POST'])
def newItem(category_id):
    category = session.query(Category).filter_by(id=category_id).one()
    if request.method=='POST':
        newItemName = request.form['name']
        newItemDescription = request.form['description']
        newItemPrice = request.form['price']
        newItem = Item(name=newItemName, description=newItemDescription, price=newItemPrice, category_id=category_id)
        session.add(newItem)
        session.commit()
        return redirect(url_for('viewItem', category_id=category.id, item_id=newItem.id))
    else:
        return render_template('newItem.html', category=category)

@app.route('/category/<int:category_id>/edit/<int:item_id>', methods=['GET','POST'])
def editItem(category_id, item_id):
    category = session.query(Category).filter_by(id=category_id).one()
    item = session.query(Item).filter_by(id=item_id).one()
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
def deleteItem(category_id, item_id):
    category = session.query(Category).filter_by(id=category_id).one()
    item = session.query(Item).filter_by(id=item_id).one()
    if request.method=='POST':
        session.delete(item)
        session.commit()
        return redirect(url_for('itemList', category_id=category.id))
    else:
        return render_template('deleteItem.html', category=category, item=item)

if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host = '0.0.0.0', port = 5000)
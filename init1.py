#Import Flask Library
from flask import Flask, render_template, request, session, url_for, redirect, json,send_file
import pymysql.cursors
from flask_bootstrap import Bootstrap
import sys
import os
import uuid
import hashlib
from functools import wraps
import time

#Initialize the app from Flask
app = Flask(__name__)
app.secret_key = "super secret key"
Bootstrap(app)

IMAGES_DIR = os.path.join(os.getcwd(), "images")

#Configure MySQL
conn = pymysql.connect(host='localhost',
                       port = 3306,
                       user='root',
                       password='mysEM8l!',
                       db='finstagram',
                       charset='utf8mb4',
                       cursorclass=pymysql.cursors.DictCursor,
                       autocommit = True)

def login_required(f):
    @wraps(f)
    def dec(*args, **kwargs):
        if not "username" in session:
            error = "You need to be logged in to access that page"
            return render_template('login.html', loginError=error)
        return f(*args, **kwargs)
    return dec

#Define route for login
@app.route('/login')
def login():
    if 'username' in session:
        return redirect(url_for('person', username=session['username']))

    return render_template('login.html')

#Define route for register
@app.route('/register')
def register():
    if "username" in session:
        session.pop('username')
    return render_template('register.html')

# auth the login
@app.route("/loginAuth", methods=["POST"])
def loginAuth():
    if request.form:
        requestData = request.form
        username = requestData["username"]
        plaintextPasword = requestData["password"]
        hashedPassword = hashlib.sha256(plaintextPasword.encode("utf-8")).hexdigest()
        with conn.cursor() as cursor:
            query = "SELECT * FROM person WHERE username = %s AND password = %s"
            cursor.execute(query, (username, hashedPassword))
        data = cursor.fetchone()
        if data:
            session["username"] = username
            return redirect(url_for("home"))

        error = "Incorrect username or password."
        return render_template("login.html", error=error)

    error = "An unknown error has occurred. Please try again."
    return render_template("login.html", error=error)

#Authenticates the register
@app.route("/registerAuth", methods=["POST"])
def registerAuth():

    if request.form:
        requestData = request.form
        username = requestData["username"]
        plaintextPasword = requestData["password"]
        hashedPassword = hashlib.sha256(plaintextPasword.encode("utf-8")).hexdigest()
        firstName = requestData["fname"]
        lastName = requestData["lname"]
        image_file = request.files.get("avatar", "")
        if not isinstance(image_file,str):
            image_name = image_file.filename
            filepath = os.path.join(IMAGES_DIR, image_name)
            image_file.save(filepath)
            noImage = False
        else:
            noImage = True
        if requestData['bio']:
            bio = requestData["bio"]
            noBio = False
        else:
            noBio = True
        isPrivate = requestData["isPrivate"]
        try:
            with conn.cursor() as cursor:
                if not noImage and not noBio:
                    query = "INSERT INTO person VALUES (%s, %s, %s, %s,%s,%s,%s)"
                    cursor.execute(query, (username, hashedPassword, firstName, lastName,image_name,bio,isPrivate))
                else:
                    if noImage:
                        query = "INSERT INTO person VALUES (%s, %s, %s, %s,NULL,%s,%s)"
                        cursor.execute(query, (username, hashedPassword, firstName, lastName,bio,isPrivate))
                    elif noBio:
                        query = "INSERT INTO person VALUES (%s, %s, %s, %s,%s,NULL,%s)"
                        cursor.execute(query, (username, hashedPassword, firstName, lastName,image_name,isPrivate))
                    
        except pymysql.err.IntegrityError:
            error = "%s is already taken." % (username)
            return render_template('register.html', error=error)    

        return redirect(url_for("login"))

    error = "An error has occurred. Please try again."
    return render_template("register.html", error=error)

# this is the function for the person's feed where he can see images
@app.route('/home')
@login_required
def home():

    username = session['username']
    cursor = conn.cursor()
    conn.commit()
    # get the photos where you follow union the photos in the groups you are in in reverse order
    query ="""
    select * from photo 
    where photoOwner in (select followeeUsername from follow where followerUsername=%s and acceptedfollow=1)
    union
    select * from photo 
    where photoID in
    (select photoID from share
    natural join belong 
    where username=%s)
    order by timestamp desc"""
    cursor.execute(query, (username,username))
    photos = cursor.fetchall()
    cursor.close()

    return render_template('home.html', session=session,photos = photos)

@app.route('/logout')
def logout():
    if not 'username' in session:
        error = "You need to be logged in to access that page"
        return render_template('login.html', loginError=error)

    session.pop('username')
    return redirect('/login')

# get the people that want to follow you
@app.route('/manage_follow_requests')
@login_required
def manage_follow_requests():
    cursor = conn.cursor()
    conn.commit()
    query = 'select * from Follow join person on followerUsername=username where followeeUsername= %s and acceptedfollow=false'
    username = session['username']
    cursor.execute(query,username)
    data = cursor.fetchall()
    cursor.close()
    return render_template('manage_follow_requests.html', follower_list=data)

# you hit the accept button, here's what happens
@app.route('/accept_follow_request', methods=['GET', 'POST'])
@login_required
def acceptFollowRequest():
    cursor = conn.cursor()
    conn.commit()
    query = 'update Follow set acceptedfollow=true where followeeUsername= %s and followerUsername= %s'
    followeeUsername = session['username']
    followerUsername = request.form['followerUsername']
    cursor.execute(query,(followeeUsername,followerUsername))
    conn.commit()
    cursor.close()
    return redirect(url_for('manage_follow_requests'))

# you hit the decline request button
@app.route('/decline_follow_request',methods=['GET','POST'])
@login_required
def declineFollowRequest():
    cursor = conn.cursor()
    conn.commit()
    query = 'delete from Follow where followeeUsername= %s and followerUsername= %s'
    followeeUsername = session['username']
    followerUsername = request.form['followerUsername']
    cursor.execute(query,(followeeUsername,followerUsername))
    conn.commit()
    cursor.close()
    return redirect(url_for('manage_follow_requests'))

# you asked to follow someone
@app.route('/request_to_follow', methods=['GET','POST'])
@login_required
def request_to_follow():
    cursor = conn.cursor()
    conn.commit()
    query = 'insert into Follow values (%s, %s, false)'
    followerUsername = session['username']
    followeeUsername = request.form['followeeUsername']
    cursor.execute(query,(followerUsername,followeeUsername))
    conn.commit()
    cursor.close()
    return redirect(url_for('person', username=followeeUsername))

# get a person's page, only showing the photos you have permission to see
@app.route('/person/<username>', methods=['GET','POST'])
@login_required
def person(username):

    #username = request.args.get('username')
    followerUsername = session['username']

    # get the photos
    cursor = conn.cursor()
    conn.commit()
    query ="""
    select photoID,filePath from photo 
    where photoOwner in (select followeeUsername from follow where followerUsername= %s and followeeUsername= %s 
    and acceptedfollow=1)
    union
    select photoID,filePath from photo 
    where photoID in
    (select photoID from share
    natural join belong 
    where username= %s)
    and photoOwner= %s
    union 
    select photoID,filePath from photo where photoOwner= %s and photoOwner=%s
    """
    cursor.execute(query,(followerUsername,username,followerUsername,username,followerUsername,username))
    photos = cursor.fetchall()
    cursor.close()

    # get the user data
    cursor=conn.cursor()
    conn.commit()
    query = 'select * from Person where username= %s'
    cursor.execute(query,username)
    person = cursor.fetchone()
    cursor.close()

    if not person:
        return redirect(url_for('home'))
        #return render_template('404.html'), 404

    # data of whether you follow him or not
    cursor=conn.cursor()
    conn.commit()
    query = 'select * from Follow where Followerusername= %s and FolloweeUsername= %s'
    cursor.execute(query,(followerUsername,username))
    follow = cursor.fetchone()
    cursor.close()
    return render_template('person.html',person=person,photos=photos,follow=follow)

# another person function which is returned by the search button
@app.route('/person', methods=['GET','POST'])
@login_required
def personSearch():
    #username = request.args.get('username')
    followerUsername = session['username']

    username = request.form['username']

    cursor = conn.cursor()
    conn.commit()
    query ="""
    select photoID,filePath from photo 
    where photoOwner in (select followeeUsername from follow where followerUsername= %s and followeeUsername= %s 
    and acceptedfollow=1)
    union
    select photoID,filePath from photo 
    where photoID in
    (select photoID from share
    natural join belong 
    where username= %s)
    and photoOwner= %s
    union 
    select photoID,filePath from photo where photoOwner= %s and photoOwner=%s
    """
    cursor.execute(query,(followerUsername,username,followerUsername,username,followerUsername,username))
    photos = cursor.fetchall()
    cursor.close()

    cursor=conn.cursor()
    conn.commit()
    query = 'select * from Person where username= %s'
    cursor.execute(query,username)
    person = cursor.fetchone()
    cursor.close()

    if not person:
        return redirect(url_for('home'))
        #return render_template('404.html'), 404

    cursor=conn.cursor()
    conn.commit()
    query = 'select * from Follow where Followerusername= %s and FolloweeUsername= %s'
    cursor.execute(query,(followerUsername,username))
    follow = cursor.fetchone()
    cursor.close()
    return render_template('person.html',person=person,photos=photos,follow=follow)

# gets the close friends group you belong to, needed when submitting a photo
@app.route('/submit_photo')
@login_required
def submit_photo():
    
    username = session['username']
    cursor = conn.cursor()
    conn.commit()
    query = 'select * from Belong where username=%s'
    cursor.execute(query,username)
    closeFriendGroups = cursor.fetchall()
    cursor.close()

    return render_template('post_photo.html', session=session, closeFriendGroups=closeFriendGroups)

# post the photo, and enter the shared info as necessary
@app.route('/post_photo', methods=['POST'])
@login_required
def post_photo():

    if request.files:
        image_file = request.files.get("imageToUpload", "")
        image_name = image_file.filename
        filepath = os.path.join(IMAGES_DIR, image_name)
        image_file.save(filepath)

        photoOwner = request.form['photoOwner']
        caption = request.form['caption']
        allFollowers = request.form['allFollowers']
        cursor = conn.cursor()
        conn.commit()
        query = 'insert into Photo values (null, %s, NOW(), %s, %s, %s)'
        cursor.execute(query,(photoOwner,image_name,caption,allFollowers))
        conn.commit()
        cursor.close()

        if allFollowers == str(0):
            cursor=conn.cursor()
            conn.commit()
            query = 'select * from Belong where username= %s'
            cursor.execute(query,photoOwner)
            groups = cursor.fetchall()
            cursor.close()
            for group in groups:
                try:
                    shareFlag = int(request.form[group['groupName']])
                except:
                    shareFlag = 0
                if(shareFlag == 1):
                    cursor=conn.cursor()
                    conn.commit()
                    query = 'insert into Share values(%s,%s,LAST_INSERT_ID())'
                    cursor.execute(query,(group['groupName'],group['groupOwner']))
                    conn.commit()
                    cursor.close()

        #return redirect(url_for('person', username=photoOwner))
        return redirect(url_for('home'))
    else:
        error = "Failed to upload image."
        return render_template("post_photo.html", error=error)

# put photo in machine
@app.route("/uploadImage", methods=["POST"])
@login_required
def upload_image():
    if request.files:
        image_file = request.files.get("imageToUpload", "")
        image_name = image_file.filename
        filepath = os.path.join(IMAGES_DIR, image_name)
        image_file.save(filepath)
        query = "INSERT INTO photo (timestamp, filePath) VALUES (%s, %s)"
        with conn.cursor() as cursor:
            cursor.execute(query, (time.strftime('%Y-%m-%d %H:%M:%S'), image_name))
        message = "Image has been successfully uploaded."
        return render_template("upload.html", message=message)
    else:
        message = "Failed to upload image."
        return render_template("upload.html", message=message)

# get a specific photo,  with tag data
@app.route('/photo/<id>', methods=['GET','POST'])
@login_required
def photo(id):

    username = session['username']

    print(username, file=sys.stdout)
    # check if user can view this photo
    cursor = conn.cursor()
    conn.commit()
    query ="""
    select exists(select photoID from photo 
    where photoOwner in (select followeeUsername from follow where followerUsername= %s and acceptedfollow=1)
    and photoID= %s
    union
    select photoID from photo 
    where photoID in
    (select photoID from share
    natural join belong 
    where username= %s)
    and photoID=%s
    union 
    select photoID from photo where photoID=%s and photoOwner= %s) as hasPermission
    """
    cursor.execute(query, (username,id,username,id,id,username))
    permission = cursor.fetchone()
    cursor.close()
    if(permission['hasPermission'] == 0):
        return redirect(url_for('home'))

    cursor = conn.cursor()
    conn.commit()
    query = 'select * from photo inner join Person on photo.photoOwner=Person.username where photoID= %s'
    cursor.execute(query, id)
    photo = cursor.fetchone()
    cursor.close()
    

    cursor = conn.cursor()
    conn.commit()
    query ='select * from tag natural join Person where acceptedTag=1 and photoID=%s'
    cursor.execute(query,id)
    tagged = cursor.fetchall()
    cursor.close()
    
    return render_template('photo.html', photo=photo, tagged=tagged)
    
@app.route("/image/<image_name>", methods=["GET"])
def image(image_name):
    image_location = os.path.join(IMAGES_DIR, image_name)
    if os.path.isfile(image_location):
        print("hi")
        return send_file(image_location, mimetype="image/jpg")

# get photo where they want to tag you in a photo
@app.route("/manage_tag_requests")
def manage_tag_requests():
    cursor = conn.cursor()
    conn.commit()
    query = 'select * from tag natural join photo where username=%s and acceptedTag=False'
    username = session['username']
    cursor.execute(query,username)
    data = cursor.fetchall()
    cursor.close()
    return render_template('manage_tag_requests.html', tag_list=data)

# you accepted the tag
@app.route('/accept_tag_request', methods=['GET', 'POST'])
@login_required
def acceptTagRequest():
    cursor = conn.cursor()
    conn.commit()
    query = 'update Tag set acceptedTag=True where username = %s and photoID= %s'
    username = session['username']
    photoID = request.form['photoID']
    cursor.execute(query,(username,photoID))
    conn.commit()
    cursor.close()
    return redirect(url_for('manage_tag_requests'))

# you declined the tag
@app.route('/decline_tag_request',methods=['GET','POST'])
@login_required
def declineTagRequest():
    cursor = conn.cursor()
    conn.commit()
    query = 'delete from tag where username= %s and photoID= %s'
    username = session['username']
    photoID = request.form['photoID']
    cursor.execute(query,(username,photoID))
    conn.commit()
    cursor.close()
    return redirect(url_for('manage_tag_requests'))

# request a tag and handle issues where already tagged etc.
@app.route('/request_tag', methods=['GET','POST'])
@login_required
def request_tag():
    username = request.form['tagee']
    photoID = request.form['photoID']

    currentUser = session["username"]

    cursor = conn.cursor()
    conn.commit()
    query = 'select exists(select username from tag where username=%s and photoID=%s) as alreadyTagged'
    cursor.execute(query, (username,photoID))
    exists = cursor.fetchone()
    cursor.close()
    if(exists['alreadyTagged'] == 1): # user already tagged, just refresh page
        return redirect(url_for('photo', id=photoID))

    if currentUser == username:
        cursor = conn.cursor()
        conn.commit()
        query = 'insert into tag values(%s,%s,true)'
        cursor.execute(query,(username,photoID))
        conn.commit()
        cursor.close()
        return redirect(url_for('photo', id=photoID))


    # check if user can view this photo
    cursor = conn.cursor()
    conn.commit()
    query ="""
    select exists(select photoID from photo 
    where photoOwner in (select followeeUsername from follow where followerUsername= %s and acceptedfollow=1)
    and photoID= %s
    union
    select photoID from photo 
    where photoID in
    (select photoID from share
    natural join belong 
    where username= %s)
    and photoID=%s
    union 
    select photoID from photo where photoID=%s and photoOwner= %s) as hasPermission
    """
    cursor.execute(query, (username,photoID,username,photoID,photoID,username))
    permission = cursor.fetchone()
    cursor.close()
    
    if(permission['hasPermission'] == 0): # no permission to view photo

        # need to get photo info to render a template and pass the error message
        cursor = conn.cursor()
        conn.commit()
        query = 'select * from photo inner join Person on photo.photoOwner=Person.username where photoID= %s'
        cursor.execute(query, photoID)
        photo = cursor.fetchone()
        cursor.close()
        

        cursor = conn.cursor()
        conn.commit()
        query ='select * from tag natural join Person where acceptedTag=1 and photoID=%s'
        cursor.execute(query,photoID)
        tagged = cursor.fetchall()
        cursor.close()
        message = " You can't tag a user that the photo wasn't shared with"

        return render_template('photo.html', photo=photo, tagged=tagged,message=message)
        #return redirect(url_for('photo', id=photoID,message=))

    else:
        cursor = conn.cursor()
        conn.commit()
        query = 'insert into tag values(%s,%s,false)'
        cursor.execute(query,(username,photoID))
        conn.commit()
        cursor.close()
        return redirect(url_for('photo', id=photoID))

# get the close friend groups you own and theyre members
@app.route('/close_friend_group', methods=['GET','POST'])
@login_required
def close_friend_group():
    username = session['username']
    cursor = conn.cursor()
    conn.commit()
    query = 'select * from closeFriendGroup where groupOwner=%s'
    cursor.execute(query,username)
    closeFriendGroups = cursor.fetchall()
    cursor.close()

    cursor = conn.cursor()
    conn.commit()
    query = 'select * from belong where groupOwner=%s'
    cursor.execute(query,username)
    users = cursor.fetchall()
    cursor.close()

    return render_template('close_friend_group.html',closeFriendGroups=closeFriendGroups,users=users)

# add someone to CFG
@app.route('/add_person_to_group', methods=['GET','POST'])
@login_required
def add_person_to_group():
    groupOwner = session['username']
    groupName = request.form['groupName']
    username = request.form['username']
    print(groupOwner, file=sys.stdout)
    print(groupName, file=sys.stdout)
    print(username, file=sys.stdout)

    # data used to render template of closeFriendGroups
    cursor = conn.cursor()
    conn.commit()
    query = 'select * from closeFriendGroup where groupOwner=%s'
    cursor.execute(query,groupOwner)
    closeFriendGroups = cursor.fetchall()
    cursor.close()

    cursor = conn.cursor()
    conn.commit()
    query = 'select * from belong where groupOwner=%s'
    cursor.execute(query,groupOwner)
    users = cursor.fetchall()
    cursor.close()

    # check if already a member
    cursor = conn.cursor()
    conn.commit()
    query = 'select exists(select * from belong where groupOwner=%s and username=%s and groupName=%s) as isMember'
    cursor.execute(query,(groupOwner,username,groupName))
    isMember = cursor.fetchone()
    cursor.close()

    if isMember["isMember"] == 1:
        error = "That person is already a member of the group!"

        return render_template('close_friend_group.html',closeFriendGroups=closeFriendGroups,users=users,error=error)
    else:
        # check if person has an account
        cursor=conn.cursor()
        conn.commit()
        query = 'select exists(select * from Person where username= %s) as isPerson'
        cursor.execute(query,username)
        isPerson = cursor.fetchone()
        cursor.close()

        if isPerson["isPerson"] == 0:
            error = "That person does not have a finstagram account"
            return render_template('close_friend_group.html',closeFriendGroups=closeFriendGroups,users=users,error=error)
        else:
            # insert the person to the group
            cursor = conn.cursor()
            conn.commit()
            query = 'insert into belong values (%s, %s, %s)'
            cursor.execute(query,(groupName,groupOwner,username))
            conn.commit()
            cursor.close()

            # get the new list of users now
            cursor = conn.cursor()
            conn.commit()
            query = 'select * from belong where groupOwner=%s'
            cursor.execute(query,groupOwner)
            users = cursor.fetchall()
            cursor.close()
            
            return render_template('close_friend_group.html',closeFriendGroups=closeFriendGroups,users=users)


#Run the app on localhost port 5000
#debug = True -> you don't have to restart flask
#for changes to go through, TURN OFF FOR PRODUCTION
if __name__ == "__main__":
    if not os.path.isdir("images"):
        os.mkdir(IMAGES_DIR)
    app.run('127.0.0.1', 5000, debug = True, reloader_type='stat')

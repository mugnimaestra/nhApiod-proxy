from flask import Flask, jsonify, request, Response
from CFSession import cfSession, cfDirectory
from CFSession import cf
import threading
import os
from typing import Union, Dict
from bs4 import BeautifulSoup
import re
import json

CACHE_DIR = os.path.join(os.getcwd(),"cache")
WEB_TARGET = "https://nhentai.net"
app = Flask(__name__)
class Renewer():
    def __init__(self,target: str):
        """Cookie renewer
        session: A valid cfSession
        target: Website url
        """
        self.renewing = False
        self.target = target
        self._thread = None
    def _renew_backend(self,session: cfSession):
        self.renewing = True
        try:
            resp = session.get(self.target)
            print(resp.status_code)
        except Exception as e:
            print(e)
        finally:
            self.renewing = False
    
    def renew(self, session: cfSession):
        "False if renewal has not started otherwise True with reason why it started"
        cookie_invalid = False
        if self.renewing:
            return {"status": False, "reason": "Is already renewing"}
        cookie_availability = session.internalHandler.cookie_available()

        cookie_status = cookie_availability[0]
        cookie_reason = cookie_availability[1]
        print(cookie_reason)
        if cookie_status:
            return {"status": False, "reason": "Cookie is valid"}
        else:
            cookie_invalid = True
        self._thread = threading.Thread(target=self._renew_backend, args=(session,))
        self._thread.start() 
        return {"status": True, "reason": cookie_reason[1] if (cookie_invalid) else "Cookie will be created soon"}

def json_resp(jsondict, status=200):
    resp = jsonify(jsondict)
    resp.status_code = status
    return resp

def conditioner(func):
    def wrapper(*args, **kwargs):
        jsonned, status = func(*args, **kwargs)
        done = jsonned.get("status")
        return {"status_code": status,"isDone": done,"json": jsonned}
    return wrapper

@conditioner
def get_json_web(response) -> Union[None, Dict]:
    if response.status_code != 200:
        return ({"status": False, "reason": "Error, backend returned %s" % response.status_code}, response.status_code)
    elif response.status_code == 404:
        return ({"status": False, "reason": "Error, cannot find what you're looking for"}, response.status_code)
    page = response.content
    soup = BeautifulSoup(page, "html.parser")
    json_regex = r'JSON\.parse\("(.*?)"\)'
    script = re.search(json_regex, (soup.find_all("script")[2].contents[0]).strip()).group(1).encode("utf-8").decode("unicode-escape")
    #IF THERE IS NO ERROR THEN PROCEED
    return (json.loads(script), 200)

@app.route("/",methods=["GET"])
def getmain():
    return json_resp({"status": False, "reason": "Invalid path"}, status=404)

@app.route("/get",methods=["GET"])
def getdata():
    if not session.internalHandler.cookie_check_expire():
        return json_resp({"status": False, "reason": "Server cookies outdated, do /getcookie to initiate renewal"}, status="403")
    try:
        code = int(request.args['id'])
    except ValueError:
        return json_resp({"status": False, "reason": "Invalid code"})
    res = session.get(f'{WEB_TARGET}/g/{code}')
    json_api = get_json_web(res)
    if not json_api.get("isDone"):
        return json_resp(json_api['json'],status=json_api["status_code"])
    return json_resp(json_api, status=200)
    #return Response(res.content, status=int(res.status_code))

@app.route("/getcookie",methods=["GET"])
def getcookie():
    renew_resp = renewer.renew(session)
    if not renew_resp["status"]: 
        return json_resp(renew_resp, status=403)
    else: 
        return json_resp(renew_resp, status=200)

@app.errorhandler(404)
def notFound(e):
    return json_resp({"code": 404, "status": "You are lost"}, status=404)

if __name__ == "__main__":
    session = cfSession(directory=cfDirectory(CACHE_DIR))
    renewer = Renewer(target=WEB_TARGET)
    app.run("0.0.0.0",port=3010)
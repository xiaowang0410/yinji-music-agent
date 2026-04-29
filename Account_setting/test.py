from pickle import LONG1

from Account_setting.login_in import Login

if __name__ == "__main__":
    login=Login()
    res=login.qr_login()
    print(res)




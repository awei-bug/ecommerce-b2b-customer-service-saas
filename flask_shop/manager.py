from flask_migrate import Migrate
from flask_cors import CORS

from flask_shop import create_app,db


app = create_app('develop')
CORS(app, supports_credentials=True)  # 解决跨域问题
# 创建同步数据库的对象
Migrate(app, db)

'''
flask db init # 初始化数据库,只执行一次
flask db migrate # 生成迁移文件
flask db upgrade # 执行迁移文件
$env:FLASK_APP = "manager"
'''
if __name__ == '__main__':
    app.run()
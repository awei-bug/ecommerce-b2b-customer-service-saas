insert into t_menus (id,name,level,path) VALUES (-1,'全部',0,Null);

insert into t_menus (id,name,level,pid) VALUES (1,'用户管理',1,-1);
insert into t_menus (id,name,level,pid) VALUES (2,'权限管理',1,-1);
insert into t_menus (id,name,level,pid) VALUES (3,'商品管理',1,-1);
insert into t_menus (id,name,level,pid) VALUES (4,'订单管理',1,-1);
insert into t_menus (id,name,level,pid) VALUES (5,'数据统计',1,-1);

insert into t_menus (id,name,level,path,pid) VALUES (11,'用户列表',2,'/user_list',1);
insert into t_menus (id,name,level,path,pid) VALUES (21,'角色列表',2,'/author_list',2);
insert into t_menus (id,name,level,path,pid) VALUES (22,'权限列表',2,'/role_list',2);
insert into t_menus (id,name,level,path,pid) VALUES (31,'商品列表',2,'/product_list',3);
insert into t_menus (id,name,level,path,pid) VALUES (32,'分类列表',2,'/group_list',3);
insert into t_menus (id,name,level,path,pid) VALUES (41,'订单列表',2,'/order_list',4);
insert into t_menus (id,name,level,path,pid) VALUES (51,'统计列表',2,'/data_list',5);

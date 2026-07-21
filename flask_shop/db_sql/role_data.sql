insert into t_roles (name,`desc`) VALUES ('管理员','普通管理权限');

select level,count(1) from t_category GROUP BY level;
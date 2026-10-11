import axios from "axios"
import router from "@/router/index.js"
import { clearAuthStorage } from "@/utils/permission.js"

const errorHandle = (status, info) => {
    switch (status) {
        case 400:
            console.log("语义错误");
            break;
        case 401:
            console.log("服务器认证失败");
            break;
        case 403:
            console.log("服务器请求拒绝执行");
            break;
        case 404:
            console.log("请检查网路请求地址");
            break;
        case 500:
            console.log("服务器发生意外");
            break;
        case 502:
            console.log("服务器无响应");
            break;
        default:
            console.log(info);
            break;
    }
}

const instance = axios.create({
    timeout: 15000,
})

instance.interceptors.request.use(
    config => {
        let token = sessionStorage.getItem("token");
        if (token) {
            config.headers.token = token
        }
        return config
    },
    error => Promise.reject(error)
)

instance.interceptors.response.use(
    response => {
        if (response.status === 200) {
            if (response.config.responseType === 'blob') {
                return Promise.resolve(response);
            }
            if (response.data && response.data.status == 401) {
                clearAuthStorage()
                router.push("/login")
            }
            if (response.data && response.data.status == 403) {
                console.warn('403', response.data.msg, response.config.url)
            }
            return Promise.resolve(response);
        }
        return Promise.reject(response);
    },
    error => {
        const { response } = error;
        if (response) {
            errorHandle(response.status, response.info)
            if (response.status === 401) {
                clearAuthStorage()
                router.push("/login")
            }
        } else if (error.code === 'ECONNABORTED') {
            error.userMessage = '请求超时，请稍后重试'
            console.warn(error.userMessage, error.config?.url)
        } else {
            error.userMessage = '无法连接后端服务'
            console.warn(error.userMessage, error.config?.url)
        }
        return Promise.reject(error)
    }
)

export default instance

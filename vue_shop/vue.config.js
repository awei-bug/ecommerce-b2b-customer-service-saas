const { defineConfig } = require('@vue/cli-service')
const AutoImport = require('unplugin-auto-import/webpack')
const Components = require('unplugin-vue-components/webpack')
const { ElementPlusResolver } = require('unplugin-vue-components/resolvers')
const apiProxyTarget = process.env.VUE_APP_API_PROXY_TARGET || 'http://127.0.0.1:5000'

module.exports = defineConfig({
  transpileDependencies: true,
  // 样板店 / Nginx：后台挂在 /admin/
  publicPath: process.env.VUE_APP_PUBLIC_PATH || '/admin/',
  devServer: {
    port: 8080,
    host: '0.0.0.0',
    // createWebHistory 的深链与刷新必须回退到 /admin/index.html，
    // 否则 /admin/module_cross 这类地址直接返回 404。
    historyApiFallback: {
      disableDotRule: true,
      rewrites: [
        { from: /^\/admin\/.*$/, to: '/admin/index.html' },
      ],
    },
    proxy: {
      '/static': { target: apiProxyTarget, changeOrigin: true },
      '^/(user|products|product|orders|order|pay|menu|roles|role|permissions|categorys|attributes|attribute|freight|expresses|dashboard|upload_img|health|api)': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
  configureWebpack: {
    plugins: [
      AutoImport({
        resolvers: [ElementPlusResolver()]
      }),
      Components({
        resolvers: [ElementPlusResolver()]
      })
    ]
  }
})

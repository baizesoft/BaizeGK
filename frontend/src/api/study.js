export async function study(path, method = 'GET', body) {
  const response = await fetch(`/api/study${path}`, { method, ...(body === undefined ? {} : {
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
  }) })
  const data = await response.json()
  if (!response.ok) {
    const detail = data.detail
    throw new Error(Array.isArray(detail) ? detail.map(x => `${x.loc?.slice(1).join('.') || '输入'}：${x.msg}`).join('；') : detail || '请求失败')
  }
  return data
}

export function unpack(file) {
  if (!file || file.size > 8 * 1024 * 1024) throw new Error('请选择不超过 8 MiB 的文件')
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onerror = () => reject(new Error('无法读取文件'))
    r.onload = () => resolve(r.result.split(',')[1])
    r.readAsDataURL(file)
  })
}

const dateFormat = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
})
export const dateText = (value) => value ? dateFormat.format(new Date(value)) : '待公布'
export const regionName = (id) => id === 'cq' ? '重庆市考' : '贵州省考·铜仁岗位'
export const materialKind = (kind) => kind === 'fixture' ? '测试材料 · 非真题' : '个人导入资料'

import axios from 'axios'
import type { ApiResponse, PicksBundle, StreamMessage } from '@/types/api'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000
})

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

export interface FetchPicksParams {
  ruleName: string
  tradeDate: string
  adjust?: string
  windowDays?: number
  limit?: number
  cursor?: string
}

/**
 * 获取选股结果（非流式）
 */
export async function fetchPicks(params: FetchPicksParams): Promise<ApiResponse<PicksBundle>> {
  const { ruleName, tradeDate, adjust = 'qfq', windowDays = 730, limit = 10, cursor = '' } = params
  const response = await api.get<ApiResponse<PicksBundle>>(
    `/picks/${ruleName}/${tradeDate}`,
    {
      params: { adjust, window_days: windowDays, limit, cursor }
    }
  )
  return response.data
}

/**
 * 获取选股结果（流式，NDJSON）
 */
export async function* fetchPicksStream(params: FetchPicksParams): AsyncGenerator<StreamMessage> {
  const { ruleName, tradeDate, adjust = 'qfq', windowDays = 730, limit = 50, cursor = '' } = params
  
  const response = await fetch(
    `/api/v1/picks/${ruleName}/${tradeDate}/stream?adjust=${adjust}&window_days=${windowDays}&limit=${limit}&cursor=${cursor}`,
    {
      method: 'GET',
      headers: {
        'Accept': 'application/x-ndjson'
      }
    }
  )

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('Response body is not readable')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.trim()) {
          const message = JSON.parse(line) as StreamMessage
          yield message
        }
      }
    }

    // 处理剩余buffer
    if (buffer.trim()) {
      const message = JSON.parse(buffer) as StreamMessage
      yield message
    }
  } finally {
    reader.releaseLock()
  }
}

export default api


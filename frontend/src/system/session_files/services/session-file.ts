import { get, post } from '@/core/lib/request';
import type { PageResult } from '@/core/types/api';
import type {
  SessionFileDetail,
  SessionFileItem,
} from '@/system/session_files/types/session-file';

export interface ListParams {
  page?: number;
  page_size?: number;
  session_id?: string;
  end_user_id?: string;
  kind?: string;
  status?: string;
  filename?: string;
}

export const sessionFileApi = {
  list: (params?: ListParams) =>
    get<PageResult<SessionFileItem>>('/v1/admin/session-files', { params }),
  get: (id: number) => get<SessionFileDetail>(`/v1/admin/session-files/${id}`),
  delete: (id: number) =>
    post<{ deleted: boolean }>(`/v1/admin/session-files/${id}/delete`, {}),
};

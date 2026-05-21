import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Suspense } from 'react';
import { RouterProvider } from 'react-router-dom';
import { Toaster } from 'sonner';

import { Spinner } from '@/core/components/common/spinner';
import '@/core/i18n';
import { router } from '@/router';

import '@/assets/styles/index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const FullscreenLoading = () => (
  <div className="flex h-screen items-center justify-center bg-[var(--color-warm)]">
    <div className="flex flex-col items-center gap-4">
      <Spinner size="lg" />
      <span className="text-sm text-stone-500">加载中...</span>
    </div>
  </div>
);

const App = () => (
  <QueryClientProvider client={queryClient}>
    <Suspense fallback={<FullscreenLoading />}>
      <RouterProvider router={router} />
    </Suspense>
    <Toaster position="top-right" richColors closeButton />
  </QueryClientProvider>
);

export default App;

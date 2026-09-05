import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Layout } from './components/Layout';
import { AnalyzePage } from './routes/AnalyzePage';
import { DemoPage } from './routes/DemoPage';
import { PredictPage } from './routes/PredictPage';
import { CalendarPage } from './routes/CalendarPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<AnalyzePage />} />
            <Route path="demo" element={<DemoPage />} />
            <Route path="predict" element={<PredictPage />} />
            <Route path="calendar" element={<CalendarPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
};

export default App;

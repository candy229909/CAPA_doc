import React from 'react';
import { render, screen } from '@testing-library/react';
import App from './App';

test('renders chat interface header', () => {
  render(<App />);
  const headerElement = screen.getByText(/AI 對話系統/);
  expect(headerElement).toBeInTheDocument();
});

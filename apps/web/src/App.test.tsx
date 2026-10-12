import {render, screen} from '@testing-library/react';
import {expect, test} from 'vitest';
import {App} from './App';
test('displays the read-only boundary and phase status', () => {
  render(<App/>);
  expect(screen.getByText('Read-only investigation — no remediation is executed.')).toBeVisible();
  expect(screen.getByRole('link', {name: 'View API schema'})).toHaveAttribute('href', 'http://localhost:8000/docs');
});

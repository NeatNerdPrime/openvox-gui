/**
 * OpenVox GUI - React Application Bootstrap
 * 
 * Entry point that initializes the React application with:
 * - MantineProvider for UI components with custom Vox Pupuli theming
 * - ThemeProvider for Casual/Formal theme switching
 * - BrowserRouter for client-side routing
 * - Notifications for toast messages and alerts
 * 
 * Theme Configuration:
 * - vporange: Vox Pupuli Orange (#EC8622) primary color
 * - vpblue: Bootstrap blue (#0D6EFD) primary color
 * - Light: Clean light mode with blue accents
 * - Dark: Clean dark mode with orange accents (color scheme from Robots!!)
 * - Robots!!: Dark mode with orange accents and animated illustrations (fun theme)
 */

import React from 'react';
import ReactDOM from 'react-dom/client';
import { MantineProvider, MantineColorScheme } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { BrowserRouter } from 'react-router';
import { App } from './App';
import { ThemeProvider, useAppTheme } from './hooks/ThemeContext';
import { lightTheme, darkTheme, robotsTheme } from './theme';
import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';
import './styles/app.css';

function ThemedApp() {
  const { theme: appTheme } = useAppTheme();
  let mantineTheme: any;
  let colorScheme: MantineColorScheme;

  if (appTheme === 'light') {
    mantineTheme = lightTheme;
    colorScheme = 'light';
  } else if (appTheme === 'dark') {
    mantineTheme = darkTheme;
    colorScheme = 'dark';
  } else { // robots
    mantineTheme = robotsTheme;
    colorScheme = 'dark';
  }

  return (
    <MantineProvider theme={mantineTheme} forceColorScheme={colorScheme}>
      <Notifications position="bottom-right" />
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </MantineProvider>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <ThemedApp />
    </ThemeProvider>
  </React.StrictMode>
);

module.exports = {
  apps: [
    {
      name: 'crypto-boom-scheduler',
      script: 'scheduler.js',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '350M',
      env: {
        NODE_ENV: 'production',
      },
      error_file: './logs/scheduler-err.log',
      out_file: './logs/scheduler-out.log',
      time: true,
    },
    {
      name: 'crypto-boom-dashboard',
      script: 'dashboard.js',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '250M',
      env: {
        NODE_ENV: 'production',
        PORT: 3000,
      },
      error_file: './logs/dashboard-err.log',
      out_file: './logs/dashboard-out.log',
      time: true,
    }
  ]
};

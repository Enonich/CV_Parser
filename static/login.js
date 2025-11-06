(function(){
  const API_BASE = 'http://localhost:8000';
  const loginForm = document.getElementById('login-form');
  const registerForm = document.getElementById('register-form');
  const showRegister = document.getElementById('show-register');
  const loginError = document.getElementById('login-error');
  const registerError = document.getElementById('register-error');

  showRegister.addEventListener('click', (e)=>{
    e.preventDefault();
    registerForm.classList.toggle('hidden');
  });

  function storeToken(token){
    localStorage.setItem('auth_token', token);
  }

  async function redirectHome(){
    // Check user role and redirect accordingly
    try {
      const token = localStorage.getItem('auth_token');
      const res = await fetch(API_BASE + '/auth/me', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        console.log('User role from /auth/me:', data.role); // Debug log
        if (data.role === 'admin') {
          console.log('Redirecting to admin page'); // Debug log
          window.location.href = '/static/admin.html';
        } else {
          console.log('Redirecting to user page'); // Debug log
          window.location.href = '/static/index.html';
        }
      } else {
        console.log('Auth check failed, redirecting to user page'); // Debug log
        window.location.href = '/static/index.html';
      }
    } catch (err) {
      console.log('Error checking auth:', err); // Debug log
      window.location.href = '/static/index.html';
    }
  }

  loginForm.addEventListener('submit', async (e)=>{
    e.preventDefault();
    loginError.classList.add('hidden');
    const fd = new FormData(loginForm);
    const payload = { email: fd.get('email'), password: fd.get('password') };
    const btn = loginForm.querySelector('button');
    const spinner = document.getElementById('login-spinner');
    btn.disabled = true; spinner.classList.remove('hidden');
    try {
      const res = await fetch(API_BASE + '/auth/login', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if(!res.ok){ throw new Error(data.detail || 'Login failed'); }
      storeToken(data.access_token);
      redirectHome();
    } catch(err){
      loginError.textContent = err.message;
      loginError.classList.remove('hidden');
    } finally { btn.disabled=false; spinner.classList.add('hidden'); }
  });

  registerForm.addEventListener('submit', async (e)=>{
    e.preventDefault();
    registerError.classList.add('hidden');
    const fd = new FormData(registerForm);
    const payload = { 
      email: fd.get('email'), 
      password: fd.get('password'),
      company: fd.get('company')
    };
    const btn = registerForm.querySelector('button');
    const spinner = document.getElementById('register-spinner');
    btn.disabled = true; spinner.classList.remove('hidden');
    try {
      const res = await fetch(API_BASE + '/auth/register', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if(!res.ok){ throw new Error(data.detail || 'Registration failed'); }
      // Auto-login after successful registration
      const loginPayload = { email: fd.get('email'), password: fd.get('password') };
      const loginRes = await fetch(API_BASE + '/auth/login', {
        method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(loginPayload)
      });
      const loginData = await loginRes.json();
      if(!loginRes.ok){ throw new Error('Auto login failed'); }
      storeToken(loginData.access_token);
      redirectHome();
    } catch(err){
      registerError.textContent = err.message;
      registerError.classList.remove('hidden');
    } finally { btn.disabled=false; spinner.classList.add('hidden'); }
  });
})();
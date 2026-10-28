/**
 * CollegeConnect — Client-Side Interactions & UI Enhancements
 */

document.addEventListener('DOMContentLoaded', () => {
  // 1. Mobile Navigation Hamburger Menu
  const mobileToggle = document.getElementById('mobileNavToggle');
  const navLinks = document.getElementById('navLinks');

  if (mobileToggle && navLinks) {
    mobileToggle.addEventListener('click', () => {
      navLinks.classList.toggle('open');
      const expanded = navLinks.classList.contains('open');
      mobileToggle.setAttribute('aria-expanded', expanded);
    });
  }

  // 2. Prevent Double Submissions & Provide Loading Feedback on Forms
  const forms = document.querySelectorAll('form[data-disable-on-submit="true"]');
  forms.forEach((form) => {
    form.addEventListener('submit', (e) => {
      // Perform basic client validation check
      if (!form.checkValidity()) {
        return; // Allow native validation tooltips
      }

      const submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn && !submitBtn.disabled) {
        const originalText = submitBtn.innerHTML;
        submitBtn.disabled = true;
        submitBtn.dataset.originalText = originalText;
        submitBtn.innerHTML = `
          <svg style="animation: spin 1s linear infinite; width: 18px; height: 18px; margin-right: 8px; vertical-align: middle; display: inline-block;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10" stroke-opacity="0.25"></circle>
            <path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round"></path>
          </svg>
          Processing...
        `;
      }
    });
  });

  // 3. Copy Reference Code to Clipboard
  const copyBtn = document.getElementById('copyRefBtn');
  if (copyBtn) {
    copyBtn.addEventListener('click', async () => {
      const refCodeElem = document.getElementById('registrationRefCode');
      if (!refCodeElem) return;

      const code = refCodeElem.innerText.trim();
      try {
        await navigator.clipboard.writeText(code);
        const originalHtml = copyBtn.innerHTML;
        copyBtn.innerHTML = '✓ Copied!';
        copyBtn.style.color = '#10B981';
        setTimeout(() => {
          copyBtn.innerHTML = originalHtml;
          copyBtn.style.color = '';
        }, 2500);
      } catch (err) {
        // Fallback for non-secure contexts
        const textarea = document.createElement('textarea');
        textarea.value = code;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        copyBtn.innerHTML = '✓ Copied!';
        setTimeout(() => {
          copyBtn.innerHTML = 'Copy Reference';
        }, 2000);
      }
    });
  }

  // 4. Auto-dismiss alerts after 6 seconds (if present)
  const alerts = document.querySelectorAll('.alert-dismissible');
  alerts.forEach((alert) => {
    setTimeout(() => {
      alert.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
      alert.style.opacity = '0';
      alert.style.transform = 'translateY(-10px)';
      setTimeout(() => alert.remove(), 400);
    }, 6000);
  });
});

// Inline CSS keyframe for spinner
const style = document.createElement('style');
style.innerHTML = `
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
`;
document.head.appendChild(style);


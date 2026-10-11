import test from 'node:test';
import assert from 'node:assert/strict';
import {isGenericITResume} from '../web/src/horizon-targets.ts';

test('generic label matches case, whitespace and Unicode hyphens', () => {
  for (const title of ['ИТ-специалист', 'ит-специалист', '  ИТ-СПЕЦИАЛИСТ  ', 'ИТ‑специалист', 'ИТ – специалист']) {
    assert.equal(isGenericITResume({title}), true, title);
  }
});
test('target position fallback is checked', () => {
  assert.equal(isGenericITResume({target_position: 'ИТ-специалист'}), true);
});
test('specific titles and other specializations remain', () => {
  for (const title of ['Backend Engineer', 'Data Scientist', 'ИТ-специалист по безопасности', 'Python разработчик', '']) {
    assert.equal(isGenericITResume({title}), false, title);
  }
  assert.equal(isGenericITResume({title: 'Python разработчик', target_position: 'ИТ-специалист'}), false);
});

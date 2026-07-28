# Tools cho ReAct Agent Cupid.
from __future__ import annotations
import json
import os
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

DATABASE_PATH = Path(__file__).resolve().parents[1] / 'config' / 'mock_database.json'

def _out(data: Any = None, code: str = '', message: str = '', details: Any = None) -> str:
    payload = {'ok': not code}
    if code:
        payload['error'] = {'code': code, 'message': message}
        if details is not None:
            payload['error']['details'] = details
    else:
        payload['data'] = data
    return json.dumps(payload, ensure_ascii=False, indent=2)

def _norm(value: str) -> str:
    value = unicodedata.normalize('NFD', value.strip().casefold())
    value = ''.join(c for c in value if unicodedata.category(c) != 'Mn')
    return ' '.join(value.replace('đ', 'd').split())

def _db() -> tuple[dict[str, Any] | None, str | None]:
    try:
        with DATABASE_PATH.open(encoding='utf-8') as file:
            data = json.load(file)
        if not isinstance(data.get('profiles'), list) or not isinstance(data.get('match_feedback'), list):
            return None, 'Database sai schema.'
        return data, None
    except (OSError, json.JSONDecodeError, AttributeError) as exc:
        return None, 'Không thể đọc mock database: {}.'.format(exc)

def _save(data: dict[str, Any]) -> str | None:
    # Ghi atomically để file cũ không hỏng nếu tiến trình bị ngắt.
    temp_path = None
    try:
        descriptor, temp_path = tempfile.mkstemp(dir=DATABASE_PATH.parent, suffix='.json')
        with os.fdopen(descriptor, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write(chr(10))
        os.replace(temp_path, DATABASE_PATH)
        return None
    except OSError as exc:
        return 'Không thể lưu mock database: {}.'.format(exc)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

def _find(data: dict[str, Any], user_id: str) -> dict[str, Any] | None:
    wanted = user_id.strip().upper()
    return next((p for p in data['profiles'] if p.get('user_id', '').upper() == wanted), None)

def _public(profile: dict[str, Any]) -> dict[str, Any]:
    fields = ('user_id', 'display_name', 'age', 'city', 'bio', 'hobbies', 'values',
              'languages', 'personality', 'lifestyle', 'deal_breakers')
    return {field: profile[field] for field in fields}

def get_user_profile(user_id: str) -> str:
    '''Lấy hồ sơ công khai theo user_id (vd. U003).

    Trả JSON ok/data.profile hoặc ok/error. Tool read-only, không trả PII và
    không phát sinh exception nghiệp vụ ra ngoài.
    '''
    try:
        if not isinstance(user_id, str) or not user_id.strip():
            return _out(code='INVALID_ARGUMENT', message='user_id phải là chuỗi không rỗng.')
        data, error = _db()
        if error:
            return _out(code='DATABASE_ERROR', message=error)
        profile = _find(data, user_id)
        if profile is None:
            return _out(code='USER_NOT_FOUND', message='Không tìm thấy hồ sơ {}.'.format(user_id))
        return _out({'profile': _public(profile)})
    except Exception as exc:
        return _out(code='INTERNAL_ERROR', message='Không thể lấy hồ sơ: {}.'.format(exc))

def search_candidates(city: str, hobbies: str | list[str], age_min: int, age_max: int) -> str:
    '''Lọc ứng viên theo city, hobbies và tuổi.

    hobbies nhận list[str] hoặc chuỗi phân tách dấu phẩy. Kết quả gồm criteria,
    count, candidates. Tool read-only; input sai trả JSON lỗi thay vì crash.
    '''
    try:
        if not isinstance(city, str) or not city.strip():
            return _out(code='INVALID_ARGUMENT', message='city phải là chuỗi không rỗng.')
        items = [x.strip() for x in hobbies.split(',')] if isinstance(hobbies, str) else hobbies
        if not isinstance(items, list) or any(not isinstance(x, str) for x in items):
            return _out(code='INVALID_ARGUMENT', message='hobbies phải là chuỗi hoặc list[str].')
        if isinstance(age_min, bool) or isinstance(age_max, bool):
            return _out(code='INVALID_ARGUMENT', message='Tuổi phải là số nguyên.')
        try:
            low, high = int(age_min), int(age_max)
        except (TypeError, ValueError):
            return _out(code='INVALID_ARGUMENT', message='Tuổi phải là số nguyên.')
        if low < 18 or high < 18:
            return _out(code='SAFETY_VIOLATION', message='Chỉ hỗ trợ người từ 18 tuổi.')
        if low > high or high > 100:
            return _out(code='INVALID_ARGUMENT', message='Cần 18 <= age_min <= age_max <= 100.')
        data, error = _db()
        if error:
            return _out(code='DATABASE_ERROR', message=error)
        wanted = {_norm(x) for x in items if x.strip()}
        results = []
        for profile in data['profiles']:
            owned = {_norm(x) for x in profile['hobbies']}
            matches = wanted & owned
            if _norm(profile['city']) != _norm(city) or not low <= profile['age'] <= high:
                continue
            if wanted and not matches:
                continue
            result = _public(profile)
            result.update(matching_hobbies=sorted(matches), matching_hobby_count=len(matches))
            results.append(result)
        results.sort(key=lambda x: (-x['matching_hobby_count'], x['user_id']))
        response = {'criteria': {'city': city, 'hobbies': items, 'age_min': low, 'age_max': high},
                    'count': len(results), 'candidates': results}
        if not results:
            response['message'] = 'Không tìm thấy ứng viên phù hợp.'
        return _out(response)
    except Exception as exc:
        return _out(code='INTERNAL_ERROR', message='Không thể tìm ứng viên: {}.'.format(exc))

def _similarity(a: list[str], b: list[str]) -> float:
    first, second = {_norm(x) for x in a}, {_norm(x) for x in b}
    return len(first & second) / len(first | second) if first or second else 0.0

def calculate_compatibility(user_a: str, user_b: str) -> str:
    '''Tính điểm deterministic cho hai user khác nhau.

    Hobbies 30, values 25, languages 10, personality 10, city 10, age 15;
    mỗi xung đột deal-breaker trừ 25. Read-only; từ chối user dưới 18 tuổi.
    '''
    try:
        if not all(isinstance(x, str) and x.strip() for x in (user_a, user_b)):
            return _out(code='INVALID_ARGUMENT', message='Hai user_id phải là chuỗi không rỗng.')
        ids = [user_a.strip().upper(), user_b.strip().upper()]
        if ids[0] == ids[1]:
            return _out(code='INVALID_ARGUMENT', message='Không thể tự ghép với chính mình.')
        data, error = _db()
        if error:
            return _out(code='DATABASE_ERROR', message=error)
        a, b = _find(data, ids[0]), _find(data, ids[1])
        missing = [uid for uid, profile in zip(ids, (a, b)) if profile is None]
        if missing:
            return _out(code='USER_NOT_FOUND', message='Không tìm thấy hồ sơ.', details=missing)
        if a['age'] < 18 or b['age'] < 18:
            return _out(code='SAFETY_VIOLATION', message='Không hỗ trợ user dưới 18 tuổi.')
        breakdown = {
            'hobbies': round(30 * _similarity(a['hobbies'], b['hobbies']), 2),
            'values': round(25 * _similarity(a['values'], b['values']), 2),
            'languages': round(10 * _similarity(a['languages'], b['languages']), 2),
            'personality': round(10 * _similarity(a['personality'], b['personality']), 2),
            'same_city': 10.0 if _norm(a['city']) == _norm(b['city']) else 0.0,
            'age_proximity': max(0.0, 15 - 2.5 * abs(a['age'] - b['age'])),
        }
        conflicts = []
        for owner, other in ((a, b), (b, a)):
            lifestyle = {_norm(x) for x in other['lifestyle']}
            for rule in owner['deal_breakers']:
                if _norm(rule) in lifestyle:
                    conflicts.append('{} không chấp nhận {} của {}.'.format(
                        owner['display_name'], rule, other['display_name']))
        breakdown['deal_breaker_penalty'] = -min(50.0, 25.0 * len(conflicts))
        score = round(max(0.0, min(100.0, sum(breakdown.values()))), 2)
        hobbies = sorted({_norm(x) for x in a['hobbies']} & {_norm(x) for x in b['hobbies']})
        values = sorted({_norm(x) for x in a['values']} & {_norm(x) for x in b['values']})
        ids.sort()
        return _out({
            'match_id': 'M-{}-{}'.format(ids[0], ids[1]),
            'score': score,
            'score_scale': '0-100',
            'breakdown': breakdown,
            'reasons': [
                'Sở thích chung: {}.'.format(', '.join(hobbies) or 'không có'),
                'Giá trị chung: {}.'.format(', '.join(values) or 'không có'),
                'Chênh {} tuổi.'.format(abs(a['age'] - b['age'])),
            ],
            'deal_breaker_conflicts': conflicts,
            'disclaimer': 'Điểm mock chỉ mang tính gợi ý, không đảm bảo quan hệ thành công.',
        })
    except Exception as exc:
        return _out(code='INTERNAL_ERROR', message='Không thể tính tương thích: {}.'.format(exc))

def save_match_feedback(match_id: str, feedback: str) -> str:
    '''Tạo/cập nhật like hoặc dislike cho match dạng M-U001-U003.

    Ghi atomically vào match_feedback; không nhận nội dung tự do, không xóa DB.
    Lỗi input, user và database được trả thành JSON thay vì raise exception.
    '''
    try:
        if not isinstance(match_id, str) or not isinstance(feedback, str):
            return _out(code='INVALID_ARGUMENT', message='match_id và feedback phải là chuỗi.')
        parts = match_id.strip().upper().split('-')
        if len(parts) != 3 or parts[0] != 'M' or parts[1] == parts[2]:
            return _out(code='INVALID_ARGUMENT', message='match_id phải có dạng M-U001-U003.')
        canonical = 'M-{}'.format('-'.join(sorted(parts[1:])))
        if match_id.strip().upper() != canonical:
            return _out(code='INVALID_ARGUMENT', message='Hãy dùng match_id {}.'.format(canonical))
        value = feedback.strip().casefold()
        if value not in {'like', 'dislike'}:
            return _out(code='INVALID_ARGUMENT', message='feedback chỉ nhận like hoặc dislike.')
        data, error = _db()
        if error:
            return _out(code='DATABASE_ERROR', message=error)
        missing = [uid for uid in parts[1:] if _find(data, uid) is None]
        if missing:
            return _out(code='USER_NOT_FOUND', message='Match chứa user không tồn tại.', details=missing)
        record = next((x for x in data['match_feedback'] if x['match_id'] == canonical), None)
        operation = 'updated'
        if record is None:
            record, operation = {'match_id': canonical, 'feedback': value}, 'created'
            data['match_feedback'].append(record)
        else:
            record['feedback'] = value
        error = _save(data)
        return _out(code='DATABASE_ERROR', message=error) if error else _out(
            {'operation': operation, 'feedback': record})
    except Exception as exc:
        return _out(code='INTERNAL_ERROR', message='Không thể lưu feedback: {}.'.format(exc))

# Schema máy đọc được để Role 3 đưa đúng contract vào system prompt.
TOOL_SCHEMAS = {
    'get_user_profile': {
        'parameters': {'user_id': 'str'}, 'side_effect': 'read-only'},
    'search_candidates': {
        'parameters': {'city': 'str', 'hobbies': 'str | list[str]',
                       'age_min': 'int', 'age_max': 'int'},
        'side_effect': 'read-only'},
    'calculate_compatibility': {
        'parameters': {'user_a': 'str', 'user_b': 'str'},
        'side_effect': 'read-only'},
    'save_match_feedback': {
        'parameters': {'match_id': 'str', 'feedback': 'like | dislike'},
        'side_effect': 'write'},
}

AVAILABLE_TOOLS = {
    'get_user_profile': get_user_profile,
    'search_candidates': search_candidates,
    'calculate_compatibility': calculate_compatibility,
    'save_match_feedback': save_match_feedback,
}

# Legacy cho app.py boilerplate; hai hàm này không đăng ký trong Cupid Agent.
def get_weather(location: str) -> str:
    if not isinstance(location, str):
        return 'LỖI: location sai kiểu.'
    data = {'ha noi': 'Thời tiết Hà Nội: 28°C, Nắng nhẹ, Độ ẩm 65%.'}
    return data.get(_norm(location), 'LỖI: Không tìm thấy thời tiết {}.'.format(location))

def search_flights(origin: str, destination: str) -> str:
    return 'Chuyến bay từ {} -> {}: VN123 (08:00) - 1,500,000 VNĐ.'.format(
        origin, destination)

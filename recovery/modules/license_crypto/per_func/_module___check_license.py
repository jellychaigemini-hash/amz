# Source Generated with Decompyle++
# File: _recover.pyc (Python 3.13)

license_path = ()() / _LICENSE_FILE
if not None():
    pass
raise FileNotFoundError('未找到激活文件')
saved = None.read_bytes()
content_bytes = None(saved, _APP_ID)
saved_data = None(content_bytes.decode())
current_mid = None.loads()
if None('mid') != current_mid:
    pass
raise ValueError('机器环境变更，请重新激活')
return {
    'message': 'License OK',
    'mid': current_mid,
    None: True }
except ImportError:
    content_bytes = _pure_aes_decrypt(saved)
    except:
        license_path.unlink(True)
    raise None
except:
    license_path.unlink(True)
raise None
except Exception:
    license_path.unlink(True)
raise None

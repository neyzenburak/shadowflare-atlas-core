"""Durable per-save Premium chronicle, with explicit evidence origins."""
from pathlib import Path
from datetime import datetime,timezone
from contextlib import contextmanager
import hashlib,json,re,sqlite3,struct,threading

SAVE_TABLE=bytes.fromhex('be66b32f016e6dc81f98a546765c3d0eaa5e9dffeaa00d4b75f661855dbbdcfb8bc34f450490811e6bc9d373c6e724ba32f3c0ec57ccc4b6c1aeaf88f284ce4afc3c9f1a56c5e2f547d9d78ccd97f07b3106e514e6da4826ac879ad8a6eb92cf0f9441b4742ad1701cd4b0c20908169bfd771d219e3635533ed0d562585f637cb58d2bd289b799a1306554409671febff4a95bf722605a6ffa1b79e917b1009c7e5229122c78059155e3a2b9f8509513807f1127cb374e5115efa7724d8349a469de20a367df1042396c2dc723e4ddedd6f959b2ad6a7dbceee03a3fca4c2568931833280b07038202438a86db383419642e7aabf1e8440cb88fa80a8ebde13b')

def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def character_name(raw):return raw[:12].split(b'\0',1)[0].decode('cp1252',errors='replace')
def save_name(value):
    name=str(value).replace('\\','/').rsplit('/',1)[-1]
    if not re.fullmatch(r'\d{4}\.ssv',name,re.I):raise ValueError('Tanınmayan karakter kayıt adı.')
    return name.lower()
def profile_id(game_dir,filename,name):
    return hashlib.sha256((str(Path(game_dir)).replace('\\','/').casefold()+'|'+save_name(filename)+'|'+name).encode('utf8')).hexdigest()[:24]

def read_save(raw):
    """Read the verified 0005 format's equipment/backpack, never edit a save."""
    if len(raw)<0x179 or raw[:16]!=b'ShadowFlare0005\0':raise ValueError('Desteklenmeyen save sürümü.')
    size=struct.unpack_from('<I',raw,0x170)[0]
    if size!=len(raw)-0x179:raise ValueError('Save henüz tamamlanmamış veya boyutu geçersiz.')
    body=bytes(SAVE_TABLE[v]^raw[0x174] for v in raw[0x179:])
    checksum=struct.unpack_from('<i',raw,0x175)[0]
    if sum(v if v<128 else v-256 for v in body)!=checksum:raise ValueError('Save sağlama toplamı uyuşmuyor.')
    if body[:0x160]!=raw[16:0x170]:raise ValueError('Save karakter başlıkları uyuşmuyor.')
    at=0x160;owned=[]
    def word():
        nonlocal at
        if at+4>len(body):raise ValueError('Eksik save alanı.')
        v=struct.unpack_from('<I',body,at)[0];at+=4;return v
    def item(position=False):
        nonlocal at
        kind,ident,instance=word(),word(),word()
        if position:word();word()
        n=word()
        if n>len(body)-at:raise ValueError('Eksik save eşya kaydı.')
        at+=n;owned.append(f'{kind}:{ident}')
    for _ in range(11):
        flag=word()
        if flag not in (0,1):raise ValueError('Geçersiz ekipman bayrağı.')
        if flag:item()
    count=word()
    if count>(len(body)-at)//24:raise ValueError('Geçersiz çanta sayısı.')
    for _ in range(count):item(True)
    return dict(name=character_name(raw[16:28]),level=struct.unpack_from('<I',raw,0x34)[0],owned=owned)

class GrailStore:
    def __init__(self,path,premium):
        self.path=Path(path);self.premium=set(premium);self.lock=threading.RLock()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self._db() as db:
            db.executescript('''PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY,name TEXT,save_file TEXT,level INTEGER,started TEXT);
                CREATE TABLE IF NOT EXISTS entries(profile TEXT,item_key TEXT,first_owned TEXT,first_pickup TEXT,first_map INTEGER,manual INTEGER NOT NULL DEFAULT 0,pickups INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(profile,item_key));
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);''')
    @contextmanager
    def _db(self):
        db=sqlite3.connect(self.path,timeout=10)
        try:
            with db:yield db
        finally:db.close()
    def setting(self,key,value=None):
        with self.lock,self._db() as db:
            if value is not None:db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,value));return value
            row=db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone();return row[0] if row else None
    def observe(self,directory,filename,name,level,owned=()):
        ident=profile_id(directory,filename,name);stamp=now()
        with self.lock,self._db() as db:
            db.execute('INSERT INTO profiles VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET level=excluded.level WHERE profiles.level!=excluded.level',(ident,name,save_name(filename),level,stamp))
            for key in set(owned)&self.premium:
                db.execute('INSERT INTO entries(profile,item_key,first_owned) VALUES(?,?,?) ON CONFLICT(profile,item_key) DO UPDATE SET first_owned=COALESCE(first_owned,excluded.first_owned)',(ident,key,stamp))
        return ident
    def collect(self,ident,key,map_id):
        if key not in self.premium:return False
        with self.lock,self._db() as db:
            if not db.execute('SELECT 1 FROM profiles WHERE id=?',(ident,)).fetchone():raise ValueError('Karakter bulunamadı.')
            old=db.execute('SELECT first_owned,first_pickup,manual FROM entries WHERE profile=? AND item_key=?',(ident,key)).fetchone()
            first=not old or not any(old)
            db.execute('''INSERT INTO entries(profile,item_key,first_pickup,first_map,pickups) VALUES(?,?,?,?,1)
                ON CONFLICT(profile,item_key) DO UPDATE SET first_pickup=COALESCE(first_pickup,excluded.first_pickup),first_map=COALESCE(first_map,excluded.first_map),pickups=pickups+1''',(ident,key,now(),map_id))
        return first
    def mark(self,ident,key,found):
        if key not in self.premium or not isinstance(found,bool):raise ValueError('Geçersiz Premium kaydı.')
        with self.lock,self._db() as db:
            if not db.execute('SELECT 1 FROM profiles WHERE id=?',(ident,)).fetchone():raise ValueError('Karakter bulunamadı.')
            db.execute('INSERT INTO entries(profile,item_key,manual) VALUES(?,?,?) ON CONFLICT(profile,item_key) DO UPDATE SET manual=excluded.manual',(ident,key,int(found)))
            if not found:db.execute('DELETE FROM entries WHERE profile=? AND item_key=? AND manual=0 AND first_owned IS NULL AND first_pickup IS NULL',(ident,key))
    def view(self,ident=None):
        with self.lock,self._db() as db:
            db.row_factory=sqlite3.Row
            profiles=[dict(r) for r in db.execute('SELECT * FROM profiles ORDER BY name,save_file')]
            if ident is not None and not any(p['id']==ident for p in profiles):raise ValueError('Karakter bulunamadı.')
            entries={r['item_key']:{k:r[k] for k in ('first_owned','first_pickup','first_map','manual','pickups')} for r in db.execute('SELECT * FROM entries WHERE profile=?',(ident,))} if ident else {}
        return dict(profiles=profiles,selected=ident,entries=entries,total=len(self.premium))

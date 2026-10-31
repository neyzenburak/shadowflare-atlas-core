; ECX=death context, stack=(desired x,y). Return EAX=x, EDX=y, ret 8.
; Trace no more than 80 world units per step against the current native judge
; plane. Cross samples reject diagonal corner cutting. Every allocated item
; survives; a blocked path uses its last walkable point. Invalid corpse anchors
; (e.g. a flying monster over water) start at the living player's position.
push ebp
mov ebp, esp
sub esp, 40
push ebx
push esi
push edi
mov esi, ecx
mov eax, [ebp+8]
mov [ebp-4], eax
mov eax, [ebp+12]
mov [ebp-8], eax
mov eax, [0x482d1c]
test eax, eax
jz unavailable
mov ebx, [eax+0x30]
test ebx, ebx
jz unavailable
cmp dword ptr [ebx+0x18], 0
jle unavailable
cmp dword ptr [ebx+0x1c], 0
jle unavailable
cmp dword ptr [ebx+0x30], 0
je unavailable
mov eax, [esi+12]
mov edx, [esi+16]
mov [ebp-12], eax
mov [ebp-16], edx
call point_ok
test eax, eax
jnz anchor
mov ecx, [0x48ce0c]
mov eax, 0x434cb0
call eax
test eax, eax
jz unavailable
mov edx, [eax+0x2e4]
mov eax, [eax+0x2e0]
mov [ebp-12], eax
mov [ebp-16], edx
call point_ok
test eax, eax
jz unavailable
anchor:
mov eax, [ebp-12]
mov edx, [ebp-16]
mov [ebp-20], eax
mov [ebp-24], edx
mov eax, [ebp-4]
sub eax, [ebp-12]
mov [ebp-28], eax
cdq
xor eax, edx
sub eax, edx
mov ecx, eax
mov eax, [ebp-8]
sub eax, [ebp-16]
mov [ebp-32], eax
cdq
xor eax, edx
sub eax, edx
cmp eax, ecx
jge max_found
mov eax, ecx
max_found:
add eax, 79
xor edx, edx
mov ecx, 80
div ecx
mov edi, eax
test edi, edi
jz finish
mov dword ptr [ebp-36], 1
trace:
mov eax, [ebp-28]
imul eax, [ebp-36]
cdq
idiv edi
add eax, [ebp-12]
mov [ebp-40], eax
mov eax, [ebp-32]
imul eax, [ebp-36]
cdq
idiv edi
add eax, [ebp-16]
push eax
mov edx, [ebp-24]
mov eax, [ebp-40]
call point_ok
test eax, eax
jz stop_trace
mov edx, [esp]
mov eax, [ebp-20]
call point_ok
test eax, eax
jz stop_trace
mov edx, [esp]
mov eax, [ebp-40]
call point_ok
test eax, eax
jz stop_trace
mov eax, [ebp-40]
mov [ebp-20], eax
pop eax
mov [ebp-24], eax
inc dword ptr [ebp-36]
cmp [ebp-36], edi
jle trace
jmp finish
stop_trace:
add esp, 4
finish:
mov eax, [ebp-20]
mov edx, [ebp-24]
cmp eax, [ebp-4]
jne adjusted
cmp edx, [ebp-8]
je leave
adjusted:
lock inc dword ptr [0x11111111]
jmp leave
unavailable:
mov eax, [ebp-4]
mov edx, [ebp-8]
leave:
pop edi
pop esi
pop ebx
mov esp, ebp
pop ebp
ret 8
point_ok:
pushad
mov ecx, edx
cdq
idiv dword ptr [ebx+0x18]
test edx, edx
jns floor_x
dec eax
floor_x:
sub eax, [ebx+0x28]
cmp eax, [ebx+0x20]
jae blocked
mov esi, eax
mov eax, ecx
cdq
idiv dword ptr [ebx+0x1c]
test edx, edx
jns floor_y
dec eax
floor_y:
sub eax, [ebx+0x2c]
cmp eax, [ebx+0x24]
jae blocked
mov ecx, [ebx+0x30]
mov ecx, [ecx+eax*4]
test byte ptr [ecx+esi*2], 1
jnz blocked
mov eax, 1
jmp result
blocked:
xor eax, eax
result:
mov [esp+28], eax
popad
ret

; Called at 441cf2, after the original modal/SEH setup. ESI = player.
pushfd
pushad
inc dword ptr [0x30002000]
cmp dword ptr [0x30002004], 1
jne normal
cmp dword ptr [0x482db0], 0
jne normal
mov edi, esi
mov ecx, dword ptr [0x48ce0c]
test ecx, ecx
jz normal
call 0x434cb0
cmp eax, edi
jne normal
cmp dword ptr [edi+0x2c], 6
jne normal
cmp dword ptr [edi+0x1a4], 0
jle normal
cmp dword ptr [edi+0x43c], 0
jne normal
call 0x1f002000
sub eax, dword ptr [0x30002050]
cmp eax, 2500
ja normal
cmp dword ptr [0x3000203c], 0
je gesture
cmp dword ptr [0x30002018], edi
jne invalid
mov eax, dword ptr [edi+0x458]
cmp eax, dword ptr [0x3000201c]
jne invalid
cmp dword ptr [0x3000203c], 1
je probes
cmp dword ptr [0x3000203c], 3
je batch
cmp dword ptr [0x3000203c], 2
jne invalid
mov ecx, dword ptr [eax+0x30]
push dword ptr [0x30002020]
call 0x4299e0
test eax, eax
jz invalid
cmp dword ptr [eax], 2
jne invalid
mov ebx, dword ptr [eax+8]
cmp ebx, dword ptr [0x30002024]
jne invalid
cmp dword ptr [ebx+0xd4], 0
jle invalid
cmp dword ptr [ebx+0x34c], 0
jne invalid
mov eax, dword ptr [ebx+0x18]
sub eax, dword ptr [0x30002048]
cdq
xor eax, edx
sub eax, edx
cmp eax, 260
ja invalid
mov eax, dword ptr [ebx+0x1c]
sub eax, dword ptr [0x3000204c]
cdq
xor eax, edx
sub eax, edx
cmp eax, 260
ja invalid
mov eax, dword ptr [edi+4]
mov dword ptr [0x30002208], eax
mov eax, dword ptr [0x30002038]
mov dword ptr [0x30002210], eax
mov eax, dword ptr [ebx+0xd4]
mov dword ptr [0x30002070], eax
push 0x30002048
push 0x30002200
mov ecx, ebx
call 0x459690
mov eax, dword ptr [ebx+0xd4]
mov dword ptr [0x30002074], eax
inc dword ptr [0x30002010]
mov dword ptr [0x30002040], 3
jmp acknowledge
batch:
mov ebp, dword ptr [0x300020b0]
cmp ebp, 64
ja invalid
test ebp, ebp
jz invalid
mov esi, 0x30002800
batch_loop:
cmp dword ptr [esi+24], 0
jne batch_next
mov ecx, 0x30002800
batch_prior:
cmp ecx, esi
jae batch_unique
mov eax, dword ptr [esi]
cmp eax, dword ptr [ecx]
jne batch_prior_next
mov eax, dword ptr [esi+4]
cmp eax, dword ptr [ecx+4]
je batch_skip
batch_prior_next:
add ecx, 32
jmp batch_prior
batch_unique:
mov eax, dword ptr [edi+0x458]
mov ecx, dword ptr [eax+0x30]
push dword ptr [esi]
call 0x4299e0
test eax, eax
jz batch_skip
cmp dword ptr [eax], 2
jne batch_skip
mov ebx, dword ptr [eax+8]
cmp ebx, dword ptr [esi+4]
jne batch_skip
mov eax, dword ptr [edi+0x458]
cmp eax, dword ptr [ebx+0x5c]
jne batch_skip
cmp dword ptr [ebx+0xd4], 0
jle batch_skip
mov eax, dword ptr [edi+4]
mov dword ptr [0x30002208], eax
mov eax, dword ptr [0x30002038]
mov dword ptr [0x30002210], eax
mov eax, dword ptr [ebx+0x18]
mov dword ptr [esi+8], eax
mov eax, dword ptr [ebx+0x1c]
mov dword ptr [esi+12], eax
mov eax, dword ptr [ebx+0xd4]
mov dword ptr [esi+16], eax
; Publish consumption before calling death/EXP/drop code: never double hit.
mov dword ptr [esi+24], 1
lea eax, [esi+8]
push eax
push 0x30002200
mov ecx, ebx
call 0x459690
mov eax, dword ptr [ebx+0xd4]
mov dword ptr [esi+20], eax
inc dword ptr [0x30002010]
jmp batch_next
batch_skip:
mov dword ptr [esi+24], 2
batch_next:
add esi, 32
dec ebp
jnz batch_loop
mov dword ptr [0x30002040], 3
jmp acknowledge
probes:
mov ebp, dword ptr [0x30002054]
cmp ebp, 64
ja invalid
test ebp, ebp
jz invalid
mov ebx, 0x30002400
probe_loop:
mov eax, dword ptr [edi+0x458]
mov ecx, dword ptr [eax+0x3c]
mov edx, ebx
mov eax, 0x30002340
call 0x30001c00
test eax, eax
jz blocked
push 1
push 2
push 0
push 0x30002340
push ebx
push -1
push dword ptr [edi+0x458]
mov ecx, 0x482df4
call 0x4145b0
cmp eax, 1
jne blocked
add ebx, 8
dec ebp
jnz probe_loop
mov dword ptr [0x30002040], 1
jmp acknowledge
blocked:
mov eax, ebx
sub eax, 0x30002400
shr eax, 3
mov dword ptr [0x30002058], eax
inc dword ptr [0x30002014]
mov dword ptr [0x30002040], 2
jmp acknowledge
invalid:
mov dword ptr [0x30002040], 4
acknowledge:
mov dword ptr [0x3000203c], 0
gesture:
cmp dword ptr [0x48ce34], 0
jne normal
cmp dword ptr [0x48d778], -1
jne normal
mov ecx, 0x48ce38
panels:
cmp dword ptr [ecx], 0
jne normal
add ecx, 4
cmp ecx, 0x48ce70
jb panels
push 0xa4
call dword ptr [0x4735c0]
test ax, 0x8000
jz normal
mov eax, dword ptr [edi+0x3f8]
cmp dword ptr [eax+0x24], 1
je right
cmp dword ptr [eax+0x2c], 1
jne normal
right:
cmp dword ptr [eax+0x2c], 1
jne consumed
cmp dword ptr [0x30002078], 0
jne consumed
cmp dword ptr [0x3000203c], 0
jne consumed
cmp dword ptr [0x3000209c], 1
je meteor_cast
mov ecx, 0x48d54c
call dword ptr [0x47334c]
test eax, eax
jle consumed
cmp eax, 10000
ja consumed
mov ebp, eax
find:
dec ebp
push ebp
mov ecx, 0x48d54c
call dword ptr [0x473350]
test eax, eax
jz next
mov ecx, eax
call dword ptr [0x473354]
mov ecx, eax
call dword ptr [0x47345c]
mov ebx, eax
push eax
mov eax, dword ptr [edi+0x458]
mov ecx, dword ptr [eax+0x30]
call 0x4299e0
test eax, eax
jz next
cmp dword ptr [eax], 2
jne next
mov esi, dword ptr [eax+8]
test esi, esi
jz next
cmp dword ptr [esi+0xd4], 0
jle next
mov dword ptr [0x30002018], edi
mov eax, dword ptr [edi+0x458]
mov dword ptr [0x3000201c], eax
mov dword ptr [0x30002020], ebx
mov dword ptr [0x30002024], esi
mov eax, dword ptr [edi+0x2e0]
mov dword ptr [0x30002028], eax
mov eax, dword ptr [edi+0x2e4]
mov dword ptr [0x3000202c], eax
mov eax, dword ptr [esi+0x18]
mov dword ptr [0x30002030], eax
mov eax, dword ptr [esi+0x1c]
mov dword ptr [0x30002034], eax
jmp attack
meteor_cast:
mov dword ptr [0x30002018], edi
mov eax, dword ptr [edi+0x458]
mov dword ptr [0x3000201c], eax
mov eax, dword ptr [edi+0x2e0]
mov dword ptr [0x30002028], eax
mov eax, dword ptr [edi+0x2e4]
mov dword ptr [0x3000202c], eax
attack:
mov eax, dword ptr [edi+0x1b4]
test eax, eax
jle consumed
cmp eax, 715827882
jle multiply
mov eax, 715827882
multiply:
imul eax, eax, 3
mov dword ptr [0x30002038], eax
mov eax, dword ptr [0x3000209c]
mov dword ptr [0x300020a4], eax
mov eax, dword ptr [0x300020a0]
mov dword ptr [0x300020a8], eax
call 0x1f002000
mov dword ptr [0x300020ac], eax
mov dword ptr [0x30002078], 1
inc dword ptr [0x30002008]
jmp consumed
next:
test ebp, ebp
jnz find
consumed:
inc dword ptr [0x3000200c]
dec dword ptr [0x30002000]
popad
popfd
jmp 0x441cad
normal:
dec dword ptr [0x30002000]
popad
popfd
mov eax, dword ptr [esi+0x3f8]
jmp 0x441cf8

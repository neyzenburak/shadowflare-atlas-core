; 41ebfd replaces a conditional branch. Preserve its flags on both exits.
pushfd
pushad
inc dword ptr [0x30002080]
cmp dword ptr [0x30002004], 1
jne done
call 0x1f002000
sub eax, dword ptr [0x30002050]
cmp eax, 2500
ja done
mov esi, dword ptr [0x30002084]
test esi, esi
jz done
mov dword ptr [0x30002088], esi
cmp esi, dword ptr [0x30002084]
jne done
cmp dword ptr [0x482db0], 0
jne done
mov ecx, dword ptr [0x48ce0c]
test ecx, ecx
jz done
call 0x434cb0
test eax, eax
jz done
cmp eax, dword ptr [esi+8]
jne done
cmp dword ptr [eax+0x1a4], 0
jle done
cmp dword ptr [eax+0x2c], 6
jne done
mov eax, dword ptr [eax+0x458]
cmp eax, dword ptr [esi+4]
jne done
mov ebp, dword ptr [esi]
cmp ebp, 4096
ja done
test ebp, ebp
jz done
mov edi, dword ptr [0x482d1c]
test edi, edi
jz done
add esi, 16
loop:
mov eax, dword ptr [esi+16]
cmp eax, dword ptr [0x300020b8]
jae next
imul eax, eax, 24
add eax, 0x30042000
mov edx, dword ptr [eax]
mov dword ptr [0x300020c0], edx
mov edx, dword ptr [eax+4]
mov dword ptr [0x300020c4], edx
mov edx, dword ptr [eax+8]
mov dword ptr [0x300020c8], edx
mov edx, dword ptr [eax+12]
mov dword ptr [0x300020cc], edx
mov edx, dword ptr [eax+16]
mov dword ptr [0x300020d0], edx
push 0x30002094
push 0x30002090
push dword ptr [esi+4]
push dword ptr [esi]
mov ecx, dword ptr [0x482d14]
call 0x1f001000
mov eax, dword ptr [0x30002090]
sub eax, dword ptr [edi+0x40]
add eax, dword ptr [esi+8]
sub eax, dword ptr [0x300020cc]
mov dword ptr [0x30002090], eax
mov edx, dword ptr [0x30002094]
sub edx, dword ptr [edi+0x44]
add edx, dword ptr [esi+12]
sub edx, dword ptr [0x300020d0]
mov dword ptr [0x30002094], edx
cmp eax, dword ptr [edi+0x18]
jg next
add eax, dword ptr [0x300020c4]
cmp eax, dword ptr [edi+0x10]
jl next
cmp edx, dword ptr [edi+0x1c]
jg next
add edx, dword ptr [0x300020c8]
cmp edx, dword ptr [edi+0x14]
jl next
push dword ptr [0x300020c0]
lea eax, [edi+0x10]
push eax
push 1000
push 1000
push 1000
push 0
push 1000
push 1000
push 1000
push 1000
push dword ptr [0x30002094]
push dword ptr [0x30002090]
push 0x1022
push -1
push 0
push 0
push dword ptr [edi+0x20]
push ebx
mov ecx, dword ptr [0x482d10]
call 0x1f000000
next:
add esi, 24
dec ebp
jnz loop
done:
mov dword ptr [0x30002088], 0
dec dword ptr [0x30002080]
popad
popfd
jne 0x41f130
jmp 0x41ec03

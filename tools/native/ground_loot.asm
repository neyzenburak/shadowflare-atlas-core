; Ground equipment visibility and a single game-thread liquidation request.
; Visibility bypasses ONLY packet submission: physics, animation and saves run.
;; @section visibility 0x0
pushfd
pushad
cmp dword ptr [@data],1
jne visibility_show
mov eax,[esi+0xcc]
test eax,eax
jz visibility_show
cmp dword ptr [eax+0xc],2
ja visibility_show
cmp dword ptr [eax+0x18],1
ja visibility_show
inc dword ptr [@data+4]
popad
popfd
jmp 0x458cc3
visibility_show:
popad
popfd
mov ecx,[esi+0xcc]
jmp 0x458a22

;; @section request 0x100
pushfd
pushad
cmp ecx,[@data+4]
jne request_exit
mov eax,1
mov edx,2
lock cmpxchg [@data],edx
jne request_exit
cmp dword ptr [0x482db0],0
jne request_fail
mov edi,ecx
mov ebx,[edi+0x458]
cmp ebx,[@data+8]
jne request_fail
cmp dword ptr [edi+0x1a4],0
jle request_fail
cmp dword ptr [0x48ce34],0
jne request_fail
mov eax,[edi+0x2e0]
mov [@data+56],eax
mov eax,[edi+0x2e4]
mov [@data+60],eax
mov esi,[@data+16]
mov ebp,[@data+12]
test ebp,ebp
jz request_done
quote_loop:
mov dword ptr [esi+8],0
mov dword ptr [esi+12],0
call @lookup
test eax,eax
jz quote_next
mov ecx,eax
call @unit_price
test eax,eax
jle quote_next
mov [esi+8],eax
mov dword ptr [esi+12],1
add [@data+32],eax
adc dword ptr [@data+36],0
inc dword ptr [@data+24]
quote_next:
add esi,16
dec ebp
jnz quote_loop
cmp dword ptr [@data+20],1
jne request_done
cmp dword ptr [@data+24],0
je request_done
call @sell
jmp request_done
request_fail:
mov dword ptr [@data+52],1
mov dword ptr [@data],4
jmp request_exit
request_done:
cmp dword ptr [@data+52],0
jne request_fail
mov dword ptr [@data],3
request_exit:
popad
popfd
sub esp,8
push ebx
push ebp
push esi
jmp 0x443496

;; @section lookup 0x400
; Validate the world ID BEFORE dereferencing a possibly collected item pointer.
push dword ptr [esi+4]
mov ecx,[ebx+0x30]
call 0x4299e0
test eax,eax
jz lookup_done
cmp dword ptr [eax],3
jne lookup_missing
mov eax,[eax+8]
test eax,eax
jz lookup_done
cmp [eax+0x5c],ebx
jne lookup_missing
mov eax,[eax+0xcc]
cmp eax,[esi]
jne lookup_missing
test eax,eax
jz lookup_done
cmp dword ptr [eax+0xc],2
ja lookup_missing
cmp dword ptr [eax+0x18],1
ja lookup_missing
ret
lookup_missing:
xor eax,eax
lookup_done:
ret

;; @section unit_price 0x500
; The merchant's sale-price argument (1), with identification temporarily OFF.
; Restore the exact flag in the same game-thread call; no identify-all occurs.
push esi
mov esi,ecx
push dword ptr [esi+0x1c]
mov dword ptr [esi+0x1c],0
push 1
call 0x4661c0
pop dword ptr [esi+0x1c]
pop esi
ret

;; @section sell 0x600
; Reserve ALL currency objects before removing any equipment. Failure here
; frees reservations and leaves every ground item intact.
mov eax,[@data+32]
mov edx,[@data+36]
mov ecx,0x7fffffff
div ecx
test edx,edx
jz sale_gold_count
inc eax
sale_gold_count:
mov [@data+44],eax
mov ebp,eax
mov esi,[@data+64]
reserve_gold:
push 0
push 0
push 4
mov ecx,[0x48ce14]
call 0x462d30
test eax,eax
jz reserve_failed
mov [esi],eax
inc dword ptr [@data+88]
add esi,20
dec ebp
jnz reserve_gold
mov esi,[@data+16]
mov ebp,[@data+12]
sale_loop:
cmp dword ptr [esi+12],1
jne sale_next
call @lookup
test eax,eax
jz sale_next
push eax
push dword ptr [esi+4]
mov ecx,ebx
call 0x427a00
cmp eax,1
jne sale_next
; Original item-bank destructor also clears its pointer argument.
push esi
mov ecx,[0x48ce14]
call 0x465640
inc dword ptr [@data+28]
mov eax,[esi+8]
add [@data+72],eax
adc dword ptr [@data+76],0
mov dword ptr [esi+12],2
sale_next:
add esi,16
dec ebp
jnz sale_loop
mov eax,[@data+72]
mov edx,[@data+76]
mov [@data+32],eax
mov [@data+36],edx
mov esi,[@data+64]
mov ebp,[@data+88]
place_gold:
mov eax,[@data+72]
or eax,[@data+76]
jz free_remaining
mov eax,0x7fffffff
cmp dword ptr [@data+76],0
jne place_amount
cmp [@data+72],eax
ja place_amount
mov eax,[@data+72]
place_amount:
mov [esi+8],eax
sub [@data+72],eax
sbb dword ptr [@data+76],0
push eax
mov ecx,[esi]
call 0x466440
push dword ptr [@data+60]
push dword ptr [@data+56]
mov ecx,[esi]
call 0x4663e0
push -1
push 0
push dword ptr [esi]
mov ecx,ebx
call 0x427970
mov [esi+4],eax
mov eax,[@data+56]
mov [esi+12],eax
mov eax,[@data+60]
mov [esi+16],eax
inc dword ptr [@data+40]
add esi,20
dec ebp
jnz place_gold
ret
reserve_failed:
mov dword ptr [@data+52],2
mov esi,[@data+64]
mov ebp,[@data+88]
free_remaining:
test ebp,ebp
jz free_done
push esi
mov ecx,[0x48ce14]
call 0x465640
add esi,20
dec ebp
jnz free_remaining
free_done:
ret

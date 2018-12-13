print("number loop")
for i=10,1,-1 do
    print(i)
end

print("number loop break")
for i=10,1,-1 do
    print('before break', i)
    if (i > 5) then
        break
    end
    print('after break', i)
end

print("number loop nest break")
for j=10,1,-1 do
    for i=10,1,-1 do
        print('before break', i)
        if (i > 5) then
            break
        end
        print('after break', i)
    end
end

print("iter loop")
a = {"one", "two", "three"}
for i, v in ipairs(a) do
    print(i, v)
end

print("iter loop break")
a = {"one", "two", "three"}
for i, v in ipairs(a) do
    print('before break', i)
    if (i > 5) then
        break
    end
    print('after break', i)
end

print("iter loop nest break")
a = {"one", "two", "three"}
for i, v in ipairs(a) do
    for i, v in ipairs(a) do
        print('before break', i)
        if (i > 5) then
            break
        end
        print('after break', i)
    end
end


print("iter loop 2")
for i, v in pairs(a) do
    print(i, v)
end


print("iter loop 2 break")
for i, v in pairs(a) do
    print('before break', i)
    if (i > 5) then
        break
    end
    print('after break', i)
end


print("iter loop 2 nest break")
for i, v in pairs(a) do
    for i, v in pairs(a) do
        print('before break', i)
        if (i > 5) then
            break
        end
        print('after break', i)
    end
end


print("while loop")
a = 10
while a < 20 do
       print(a)
       a = a+1
end

print("while loop break")
a = 10
while a < 20 do
    print('before break', i)
    if (i > 5) then
        break
    end
    print('after break', i)
end


print("while loop nest break")
a = 10
while a < 20 do
    while a < 20 do
        print('before break', i)
        if (i > 5) then
            break
        end
        print('after break', i)
    end
end


print("repeat loop")
a = 10
repeat
   print("value of a:", a)
   a = a + 1
until( a > 15 )


print("repeat loop break")
a = 10
repeat
    print('before break', i)
    if (i > 5) then
        break
    end
    print('after break', i)
until( a > 15 )


print("repeat loop nest break")
a = 10
repeat
    repeat
        print('before break', i)
        if (i > 5) then
            break
        end
        print('after break', i)
    until( a > 15 )
until( a > 16 )


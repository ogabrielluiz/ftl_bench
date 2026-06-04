-- ftl_bench pure-Lua JSON encoder. Sandbox-safe: uses only
-- string/table/math/pairs/ipairs/type/tostring. Installs _G.json.
local json = {}

local function escape_string(s)
  local result = {}
  for i = 1, #s do
    local c = string.byte(s, i)
    if c == 34 then result[#result+1] = '\\"'
    elseif c == 92 then result[#result+1] = '\\\\'
    elseif c == 8 then result[#result+1] = '\\b'
    elseif c == 12 then result[#result+1] = '\\f'
    elseif c == 10 then result[#result+1] = '\\n'
    elseif c == 13 then result[#result+1] = '\\r'
    elseif c == 9 then result[#result+1] = '\\t'
    elseif c < 32 or c > 126 then result[#result+1] = string.format('\\u%04x', c)
    else result[#result+1] = string.sub(s, i, i)
    end
  end
  return table.concat(result)
end

local function encode_value(v, seen)
  seen = seen or {}
  local vtype = type(v)
  if vtype == 'nil' then
    return 'null'
  elseif vtype == 'boolean' then
    return v and 'true' or 'false'
  elseif vtype == 'number' then
    if v ~= v then return 'null' end
    if v == math.huge or v == -math.huge then return 'null' end
    if math.floor(v) == v then return string.format('%d', v) end
    return string.format('%.14g', v)
  elseif vtype == 'string' then
    return '"' .. escape_string(v) .. '"'
  elseif vtype == 'table' then
    if seen[v] then return 'null' end
    seen[v] = true
    local is_array = true
    local len = 0
    for k in pairs(v) do
      if type(k) ~= 'number' or k < 1 or math.floor(k) ~= k then
        is_array = false
        break
      end
      if k > len then len = k end
    end
    if is_array then
      for i = 1, len do
        if v[i] == nil then is_array = false break end
      end
    end
    local parts = {}
    if is_array then
      for i = 1, len do parts[i] = encode_value(v[i], seen) end
      seen[v] = nil
      return '[' .. table.concat(parts, ',') .. ']'
    else
      for k in pairs(v) do
        local ktype = type(k)
        if ktype == 'string' then
          parts[#parts+1] = '"' .. escape_string(k) .. '":' .. encode_value(v[k], seen)
        elseif ktype == 'number' then
          parts[#parts+1] = '"' .. tostring(k) .. '":' .. encode_value(v[k], seen)
        end
      end
      seen[v] = nil
      return '{' .. table.concat(parts, ',') .. '}'
    end
  else
    return 'null'
  end
end

function json.encode(value)
  return encode_value(value, {})
end

-- Minimal decoder reserved for M2 (not used in M1).
function json.decode(str)
  local pos = 1
  local parse_value
  local function skip_ws()
    while pos <= #str and string.match(string.sub(str, pos, pos), '[\r\n\t ]') do pos = pos + 1 end
  end
  local function parse_string()
    pos = pos + 1
    local start = pos
    while pos <= #str do
      local c = string.sub(str, pos, pos)
      if c == '"' then local r = string.sub(str, start, pos - 1) pos = pos + 1 return r
      elseif c == '\\' then pos = pos + 2
      else pos = pos + 1 end
    end
    return ''
  end
  local function parse_number()
    local start = pos
    while pos <= #str and string.match(string.sub(str, pos, pos), '[0-9eE%+%-%.]') do pos = pos + 1 end
    return tonumber(string.sub(str, start, pos - 1))
  end
  local function parse_array()
    pos = pos + 1 skip_ws()
    local r = {}
    if string.sub(str, pos, pos) ~= ']' then
      repeat
        r[#r+1] = parse_value() skip_ws()
        if string.sub(str, pos, pos) == ',' then pos = pos + 1 end
      until string.sub(str, pos, pos) == ']'
    end
    pos = pos + 1 return r
  end
  local function parse_object()
    pos = pos + 1 skip_ws()
    local r = {}
    if string.sub(str, pos, pos) ~= '}' then
      repeat
        skip_ws() local key = parse_string() skip_ws()
        pos = pos + 1 r[key] = parse_value() skip_ws()
        if string.sub(str, pos, pos) == ',' then pos = pos + 1 end
      until string.sub(str, pos, pos) == '}'
    end
    pos = pos + 1 return r
  end
  parse_value = function()
    skip_ws()
    local c = string.sub(str, pos, pos)
    if c == '"' then return parse_string()
    elseif c == '{' then return parse_object()
    elseif c == '[' then return parse_array()
    elseif c == 't' then pos = pos + 4 return true
    elseif c == 'f' then pos = pos + 5 return false
    elseif c == 'n' then pos = pos + 4 return nil
    else return parse_number() end
  end
  return parse_value()
end

_G.json = json

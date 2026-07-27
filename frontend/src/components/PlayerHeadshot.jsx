import { useEffect, useMemo, useState } from "react"

function normalizePlayerImageName(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9\s-]/g, " ")
    .replace(/-/g, " ")
    .replace(/\b(jr|sr|ii|iii|iv|v)\b/g, "")
    .replace(/\s+/g, " ")
    .trim()
}

function getBasketballReferenceImageCandidates(playerName) {
  const cleanName = normalizePlayerImageName(playerName)
  if (!cleanName) return []

  const manualSlugs = {
    "kareem abdul jabbar": ["abdulka01"],
    "shaquille oneal": ["onealsh01"],
    "shaquille o neal": ["onealsh01"],
    "hakeem olajuwon": ["olajuha01"],
    "julius erving": ["ervinju01"],
    "michael jordan": ["jordami01"],
    "lebron james": ["jamesle01"],
    "kobe bryant": ["bryanko01"],
    "larry bird": ["birdla01"],
    "magic johnson": ["johnsma02", "johnsma01"],
    "wilt chamberlain": ["chambwi01"],
    "bill russell": ["russebi01"],
    "tim duncan": ["duncati01"],
    "stephen curry": ["curryst01"],
    "steph curry": ["curryst01"],
    "kevin durant": ["duranke01"],
    "allen iverson": ["iversal01"],
    "charles barkley": ["barklch01"],
    "jason kidd": ["kiddja01"],
    "jack sikma": ["sikmaja01"],
    "vince carter": ["cartevi01"],
    "tracy mcgrady": ["mcgratr01"],
    "dominique wilkins": ["wilkido01"],
    "david robinson": ["robinda01"],
    "grant hill": ["hillgr01"],
    "reggie miller": ["millere01"],
    "ray allen": ["allenra02", "allenra01"],
    "dirk nowitzki": ["nowitdi01"],
    "steve nash": ["nashst01"],
    "john stockton": ["stockjo01"],
    "chris paul": ["paulch01"],
    "dwight howard": ["howardw01"],
    "yao ming": ["mingya01"],
    "dikembe mutombo": ["mutomdi01"],
    "clyde drexler": ["drexlcl01"],
    "shawn kemp": ["kempsh01"],
    "pete maravich": ["maravpe01"],
    "earl monroe": ["monroea01"],
    "walt frazier": ["fraziwa01"],
    "bernard king": ["kingbe01"],
    "elvin hayes": ["hayesel01"],
    "bob mcadoo": ["mcadobo01"],
    "gary payton": ["paytoga01"],
    "pau gasol": ["gasolpa01"],
    "manu ginobili": ["ginobma01"],
    "carmelo anthony": ["anthoca01"],
    "jerry west": ["westje01"],
    "anthony edwards": ["edwaran01"],
    "ja morant": ["moranja01"],
    "nikola jokic": ["jokicni01"],
    "luka doncic": ["doncilu01"],
    "victor wembanyama": ["wembavi01"],
    "damian lillard": ["lillada01"],
    "kyrie irving": ["irvinky01"],
    "russell westbrook": ["westbru01"],
    "dwyane wade": ["wadedw01"],
    "giannis antetokounmpo": ["antetgi01"]
  }

  const tokens = cleanName.split(" ").filter(Boolean)
  const first = tokens[0] || ""
  const generatedBases = []

  function addBase(lastName, firstName = first) {
    const last = String(lastName || "").replace(/[^a-z]/g, "")
    const firstPart = String(firstName || "").replace(/[^a-z]/g, "")
    if (last.length < 2 || firstPart.length < 1) return
    generatedBases.push(`${last.slice(0, 5)}${firstPart.slice(0, 2)}`)
  }

  if (tokens.length >= 2) {
    addBase(tokens[tokens.length - 1])
    if (tokens.length >= 3) addBase(tokens[tokens.length - 2])
    if (tokens.length >= 4) addBase(`${tokens[tokens.length - 2]}${tokens[tokens.length - 1]}`)
  }

  const bases = [
    ...(manualSlugs[cleanName] || []),
    ...generatedBases.flatMap(base => ["01", "02", "03", "04", "05"].map(number => `${base}${number}`))
  ]

  return [...new Set(bases.filter(Boolean))].map(
    slug => `https://www.basketball-reference.com/req/202106291/images/players/${slug}.jpg`
  )
}

export default function PlayerHeadshot({
  player,
  playerName,
  fallbackUrl = "",
  className = "idea-lab-player-image",
  alt
}) {
  const name = String(playerName || player?.name || player?.player || "").trim()
  const cacheKey = `${name.toLowerCase()}::bref_headshot_original_v2`
  const basketballReferenceSources = useMemo(
    () => getBasketballReferenceImageCandidates(name),
    [name]
  )
  const [imageSources, setImageSources] = useState([])
  const [imageIndex, setImageIndex] = useState(0)
  const [resolvedImage, setResolvedImage] = useState("")

  useEffect(() => {
    let active = true

    if (!name) {
      setImageSources([])
      setImageIndex(0)
      setResolvedImage("")
      return () => {
        active = false
      }
    }

    window.__courtvisionPlayerImageCache = window.__courtvisionPlayerImageCache || {}
    const cached = window.__courtvisionPlayerImageCache[cacheKey]

    if (cached !== undefined) {
      setImageSources(cached ? [cached] : [])
      setImageIndex(0)
      setResolvedImage(cached || "")
      return () => {
        active = false
      }
    }

    setImageSources(basketballReferenceSources)
    setImageIndex(0)
    setResolvedImage("")

    const wikipediaSlug = encodeURIComponent(name.replace(/\s+/g, "_"))

    fetch(`https://en.wikipedia.org/api/rest_v1/page/summary/${wikipediaSlug}`)
      .then(response => (response.ok ? response.json() : null))
      .then(data => {
        if (!active) return
        const wikiImage = data?.thumbnail?.source || data?.originalimage?.source || ""
        if (!wikiImage) return

        setImageSources(previous => (
          previous.includes(wikiImage) ? previous : [...previous, wikiImage]
        ))
      })
      .catch(() => {})

    return () => {
      active = false
    }
  }, [basketballReferenceSources, cacheKey, name])

  const currentSource = resolvedImage || imageSources[imageIndex] || fallbackUrl || ""

  function handleImageLoad(event) {
    const source = event?.currentTarget?.src || currentSource
    if (!source || source === fallbackUrl) return

    window.__courtvisionPlayerImageCache = window.__courtvisionPlayerImageCache || {}
    window.__courtvisionPlayerImageCache[cacheKey] = source
    setResolvedImage(source)
  }

  function handleImageError() {
    const nextIndex = imageIndex + 1

    if (nextIndex < imageSources.length) {
      setImageIndex(nextIndex)
      return
    }

    window.__courtvisionPlayerImageCache = window.__courtvisionPlayerImageCache || {}
    window.__courtvisionPlayerImageCache[cacheKey] = ""
    setResolvedImage("")
  }

  if (currentSource) {
    return (
      <img
        src={currentSource}
        className={className}
        loading="lazy"
        decoding="async"
        draggable={false}
        onLoad={handleImageLoad}
        onError={handleImageError}
        alt={alt || name || "Player"}
      />
    )
  }

  return (
    <div className={`${className} placeholder`} role="img" aria-label={alt || name || "Player"}>
      <span>{String(name || "?").slice(0, 1)}</span>
    </div>
  )
}

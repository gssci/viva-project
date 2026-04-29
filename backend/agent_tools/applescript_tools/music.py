from typing import Optional

from langchain_core.tools import tool

from .core import (
    applescript_list,
    escape_applescript_string,
    parse_csv_values,
    run_applescript,
)


MUSIC_SEARCH_TYPES = {
    "all": "",
    "songs": "only songs",
    "albums": "only albums",
    "artists": "only artists",
    "composers": "only composers",
    "displayed": "only displayed",
}

REPEAT_MODES = {"off", "one", "all"}


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _track_summary_handler() -> str:
    return '''
on vivaTrackSummary(trackItem)
    set trackName to ""
    set trackArtist to ""
    set trackAlbum to ""
    set trackDuration to ""
    set trackRating to ""
    set trackLoved to ""
    try
        set trackName to name of trackItem
    end try
    try
        set trackArtist to artist of trackItem
    end try
    try
        set trackAlbum to album of trackItem
    end try
    try
        set trackDuration to duration of trackItem as integer
    end try
    try
        set trackRating to rating of trackItem
    end try
    try
        if loved of trackItem then set trackLoved to " | loved"
    end try

    set output to trackName
    if trackArtist is not "" then set output to output & " | " & trackArtist
    if trackAlbum is not "" then set output to output & " | " & trackAlbum
    if trackDuration is not "" then set output to output & " | " & trackDuration & "s"
    if trackRating is not "" then set output to output & " | rating: " & trackRating
    set output to output & trackLoved
    return output
end vivaTrackSummary
'''


def _playlist_lookup_script(
    playlist_name: str,
    variable_name: str = "targetPlaylist",
    playlist_collection: str = "playlists",
) -> str:
    safe_name = escape_applescript_string(playlist_name)
    return f'''
        set {variable_name} to missing value
        repeat with playlistItem in {playlist_collection}
            if name of playlistItem is "{safe_name}" then
                set {variable_name} to playlistItem
                exit repeat
            end if
        end repeat
    '''


@tool
def get_music_playback_status() -> str:
    """
    Gets the current Apple Music playback status and current track details.
    Call this tool when the user asks what is playing, whether Music is playing, or for current track metadata.
    """
    script = f'''
    {_track_summary_handler()}

    tell application "Music"
        set stateText to player state as text
        set positionText to ""
        try
            set positionText to player position as integer
        end try

        if stateText is "stopped" then
            return "Music is stopped."
        end if

        try
            set trackText to my vivaTrackSummary(current track)
            if positionText is not "" then
                return "Music is " & stateText & " at " & positionText & "s: " & trackText
            end if
            return "Music is " & stateText & ": " & trackText
        on error
            return "Music is " & stateText & ". No current track details are available."
        end try
    end tell
    '''
    return run_applescript(script)


@tool
def control_music_playback(action: str, position_seconds: Optional[int] = None) -> str:
    """
    Controls Apple Music playback.
    Call this tool when the user asks to play, pause, stop, skip, go back, restart the track, fast-forward, rewind, or seek.

    Args:
        action: One of "play", "pause", "playpause", "stop", "next track", "previous track", "back track", "fast forward", "rewind", or "seek".
        position_seconds: Required only for "seek"; the target playback position in seconds.
    """
    valid_actions = {
        "play",
        "pause",
        "playpause",
        "stop",
        "next track",
        "previous track",
        "back track",
        "fast forward",
        "rewind",
        "seek",
    }
    normalized = action.strip().lower()
    if normalized not in valid_actions:
        return f"Invalid Music action. Supported actions are: {', '.join(sorted(valid_actions))}"
    if normalized == "seek":
        if position_seconds is None:
            return "position_seconds is required when action is 'seek'."
        position_seconds = max(0, position_seconds)
        script = f'''
        tell application "Music"
            set player position to {position_seconds}
            return "Music playback position set to {position_seconds}s."
        end tell
        '''
        return run_applescript(script)

    script = f'''
    tell application "Music"
        {normalized}
        return "Executed Music command: {normalized}."
    end tell
    '''
    return run_applescript(script)


@tool
def set_music_playback_options(
    volume: Optional[int] = None,
    shuffle: Optional[bool] = None,
    repeat_mode: Optional[str] = None,
) -> str:
    """
    Sets Apple Music playback options such as app volume, shuffle, and repeat.
    Call this tool when the user asks to change Music volume, enable shuffle, disable shuffle, or set repeat mode.

    Args:
        volume: Optional Music app volume from 0 to 100.
        shuffle: Optional True to enable shuffle, False to disable it.
        repeat_mode: Optional repeat mode. Must be exactly one of "off", "one", or "all".
    """
    if volume is None and shuffle is None and repeat_mode is None:
        return "No Music playback options were provided."

    update_lines: list[str] = []
    messages: list[str] = []
    if volume is not None:
        volume = _clamp(volume, 0, 100)
        update_lines.append(f"set sound volume to {volume}")
        messages.append(f"volume {volume}%")
    if shuffle is not None:
        shuffle_value = "true" if shuffle else "false"
        update_lines.append(f"set shuffle enabled to {shuffle_value}")
        messages.append("shuffle on" if shuffle else "shuffle off")
    if repeat_mode is not None:
        normalized_repeat = repeat_mode.strip().lower()
        if normalized_repeat not in REPEAT_MODES:
            return "Invalid repeat_mode. Supported values are: off, one, all."
        update_lines.append(f"set song repeat to {normalized_repeat}")
        messages.append(f"repeat {normalized_repeat}")

    updates = "\n        ".join(update_lines)
    script = f'''
    tell application "Music"
        {updates}
        return "Music playback options updated: {escape_applescript_string(", ".join(messages))}."
    end tell
    '''
    return run_applescript(script)


@tool
def search_music_library(
    query: str,
    search_type: str = "songs",
    playlist_name: Optional[str] = None,
    max_results: int = 10,
) -> str:
    """
    Searches the user's Apple Music library or a specific playlist.
    Call this tool when the user asks to find songs, artists, albums, or tracks in Music before playing or building playlists.

    Args:
        query: Search text.
        search_type: One of "all", "songs", "albums", "artists", "composers", or "displayed".
        playlist_name: Optional playlist to search instead of the whole library.
        max_results: Maximum results to return, from 1 to 50.
    """
    if not query.strip():
        return "Music search query cannot be empty."

    normalized_type = search_type.strip().lower()
    if normalized_type not in MUSIC_SEARCH_TYPES:
        return "Invalid search_type. Supported values are: all, songs, albums, artists, composers, displayed."

    safe_query = escape_applescript_string(query)
    max_results = _clamp(max_results, 1, 50)
    search_modifier = f" {MUSIC_SEARCH_TYPES[normalized_type]}" if MUSIC_SEARCH_TYPES[normalized_type] else ""
    source_script = _playlist_lookup_script(playlist_name, "sourcePlaylist") if playlist_name else "set sourcePlaylist to library playlist 1"
    missing_playlist_check = 'if sourcePlaylist is missing value then return "No matching Music playlist found."' if playlist_name else ""

    script = f'''
    {_track_summary_handler()}

    tell application "Music"
        {source_script}
        {missing_playlist_check}
        set foundTracks to (search sourcePlaylist for "{safe_query}"{search_modifier})
        set output to ""
        set resultCount to 0

        repeat with trackItem in foundTracks
            set resultCount to resultCount + 1
            set output to output & "- " & my vivaTrackSummary(trackItem) & "\\n"
            if resultCount is greater than or equal to {max_results} then return output
        end repeat

        if output is "" then return "No Music tracks found."
        return output
    end tell
    '''
    return run_applescript(script)


@tool
def play_music_track(
    query: str,
    artist: Optional[str] = "",
    album: Optional[str] = "",
    playlist_name: Optional[str] = None,
    shuffle: bool = False,
) -> str:
    """
    Searches for and plays a specific song or track in Apple Music.
    Call this tool when the user asks to play a particular song, optionally by artist, album, or from a named playlist.

    Args:
        query: Song or track title search text.
        artist: Optional artist filter.
        album: Optional album filter.
        playlist_name: Optional playlist to search instead of the whole library.
        shuffle: True to enable shuffle before playing.
    """
    if not query.strip():
        return "Music track query cannot be empty."

    safe_query = escape_applescript_string(query)
    safe_artist = escape_applescript_string(artist)
    safe_album = escape_applescript_string(album)
    shuffle_value = "true" if shuffle else "false"
    source_script = _playlist_lookup_script(playlist_name, "sourcePlaylist") if playlist_name else "set sourcePlaylist to library playlist 1"
    missing_playlist_check = 'if sourcePlaylist is missing value then return "No matching Music playlist found."' if playlist_name else ""

    script = f'''
    {_track_summary_handler()}

    tell application "Music"
        {source_script}
        {missing_playlist_check}
        set foundTracks to (search sourcePlaylist for "{safe_query}" only songs)
        set targetTrack to missing value

        repeat with trackItem in foundTracks
            set artistMatches to true
            set albumMatches to true
            if "{safe_artist}" is not "" then
                set artistMatches to false
                try
                    if artist of trackItem contains "{safe_artist}" then set artistMatches to true
                end try
            end if
            if "{safe_album}" is not "" then
                set albumMatches to false
                try
                    if album of trackItem contains "{safe_album}" then set albumMatches to true
                end try
            end if
            if artistMatches and albumMatches then
                set targetTrack to trackItem
                exit repeat
            end if
        end repeat

        if targetTrack is missing value then return "No matching Music track found."
        try
            set shuffle enabled to {shuffle_value}
        end try
        play targetTrack
        return "Now playing: " & my vivaTrackSummary(targetTrack)
    end tell
    '''
    return run_applescript(script)


@tool
def list_music_playlists(query: Optional[str] = "", max_results: int = 50) -> str:
    """
    Lists Apple Music playlists, optionally filtered by name.
    Call this tool when the user asks what playlists they have or before playing or modifying a playlist.

    Args:
        query: Optional playlist name filter.
        max_results: Maximum playlists to return, from 1 to 100.
    """
    safe_query = escape_applescript_string(query)
    max_results = _clamp(max_results, 1, 100)

    script = f'''
    tell application "Music"
        set output to ""
        set resultCount to 0

        repeat with playlistItem in playlists
            set playlistName to name of playlistItem
            if "{safe_query}" is "" or playlistName contains "{safe_query}" then
                set resultCount to resultCount + 1
                set trackCount to 0
                try
                    set trackCount to count of tracks of playlistItem
                end try
                set output to output & "- " & playlistName & " | tracks: " & trackCount & "\\n"
                if resultCount is greater than or equal to {max_results} then return output
            end if
        end repeat

        if output is "" then return "No Music playlists found."
        return output
    end tell
    '''
    return run_applescript(script)


@tool
def play_music_playlist(playlist_name: str, shuffle: bool = True) -> str:
    """
    Plays a named Apple Music playlist.
    Call this tool when the user asks to play a playlist, mix, station-like playlist, or saved Apple Music collection by name.

    Args:
        playlist_name: Exact playlist name to play.
        shuffle: True to enable shuffle before playing.
    """
    if not playlist_name.strip():
        return "Music playlist name cannot be empty."

    shuffle_value = "true" if shuffle else "false"
    script = f'''
    tell application "Music"
        {_playlist_lookup_script(playlist_name)}
        if targetPlaylist is missing value then return "No matching Music playlist found."
        if (count of tracks of targetPlaylist) = 0 then return "Music playlist is empty."

        try
            set shuffle enabled to {shuffle_value}
        end try
        try
            set shuffle of targetPlaylist to {shuffle_value}
        end try

        try
            play targetPlaylist
        on error
            play track 1 of targetPlaylist
        end try
        return "Playing Music playlist: " & name of targetPlaylist
    end tell
    '''
    return run_applescript(script)


@tool
def play_music_recommendations(preference: Optional[str] = "", shuffle: bool = True) -> str:
    """
    Plays a personalized or recommendation-style Apple Music playlist when one exists in the user's library.
    Call this tool when the user asks for recommended music, their personal mix, favorites mix, new music mix, chill mix, or music chosen for them.

    Args:
        preference: Optional hint such as "new music", "favorites", "chill", "energetic", or a genre.
        shuffle: True to enable shuffle before playing.
    """
    terms = parse_csv_values(preference, max_items=8)
    if not terms:
        terms = [
            "recommended",
            "recommend",
            "for you",
            "made for you",
            "personal",
            "favorites mix",
            "favourites mix",
            "new music mix",
            "chill mix",
            "get up mix",
            "heavy rotation",
            "replay",
            "raccomand",
            "preferit",
            "novita",
            "rilass",
        ]

    shuffle_value = "true" if shuffle else "false"
    script = f'''
    tell application "Music"
        set recommendationTerms to {applescript_list(terms)}
        set targetPlaylist to missing value

        repeat with termItem in recommendationTerms
            set termText to termItem as text
            repeat with playlistItem in playlists
                set playlistName to name of playlistItem
                if playlistName contains termText then
                    try
                        if (count of tracks of playlistItem) > 0 then
                            set targetPlaylist to playlistItem
                            exit repeat
                        end if
                    end try
                end if
            end repeat
            if targetPlaylist is not missing value then exit repeat
        end repeat

        try
            set shuffle enabled to {shuffle_value}
        end try

        if targetPlaylist is not missing value then
            try
                set shuffle of targetPlaylist to {shuffle_value}
            end try
            try
                play targetPlaylist
            on error
                play track 1 of targetPlaylist
            end try
            return "Playing recommended Music playlist: " & name of targetPlaylist
        end if

        if (count of tracks of library playlist 1) = 0 then return "No recommendation playlist or library tracks were found in Music."
        play some track of library playlist 1
        return "No recommendation playlist was found, so I started a random track from your Music library."
    end tell
    '''
    return run_applescript(script)


@tool
def create_music_playlist(
    playlist_name: str,
    track_queries: Optional[str] = "",
    replace_existing: bool = False,
) -> str:
    """
    Creates an Apple Music playlist and optionally adds tracks by search query.
    Call this tool when the user asks to create a playlist from specific songs or a comma-separated list of tracks.

    Args:
        playlist_name: Playlist name.
        track_queries: Optional comma-separated song searches. The first matching song for each query is added.
        replace_existing: True to delete and recreate an existing playlist with the same name. Defaults to False.
    """
    if not playlist_name.strip():
        return "Music playlist name cannot be empty."

    queries = parse_csv_values(track_queries, max_items=100)
    replace_value = "true" if replace_existing else "false"

    script = f'''
    tell application "Music"
        set newPlaylistName to "{escape_applescript_string(playlist_name)}"
        set shouldReplace to {replace_value}
        set existingPlaylists to (every user playlist whose name is newPlaylistName)

        if (count of existingPlaylists) > 0 then
            if shouldReplace then
                delete item 1 of existingPlaylists
            else
                return "A Music playlist named '" & newPlaylistName & "' already exists. Set replace_existing to true to replace it."
            end if
        end if

        set targetPlaylist to make new user playlist with properties {{name:newPlaylistName}}
        set trackQueries to {applescript_list(queries)}
        set addedCount to 0
        set missingOutput to ""

        repeat with queryItem in trackQueries
            set queryText to queryItem as text
            set foundTracks to (search library playlist 1 for queryText only songs)
            if (count of foundTracks) > 0 then
                try
                    duplicate item 1 of foundTracks to targetPlaylist
                    set addedCount to addedCount + 1
                on error
                    set missingOutput to missingOutput & queryText & ", "
                end try
            else
                set missingOutput to missingOutput & queryText & ", "
            end if
        end repeat

        set output to "Created Music playlist '" & newPlaylistName & "' with " & addedCount & " tracks."
        if missingOutput is not "" then set output to output & " Not found or not added: " & missingOutput
        return output
    end tell
    '''
    return run_applescript(script)


@tool
def add_tracks_to_music_playlist(
    playlist_name: str,
    track_queries: str,
    create_if_missing: bool = False,
    max_matches_per_query: int = 1,
) -> str:
    """
    Adds tracks to an existing Apple Music playlist by searching the library.
    Call this tool when the user asks to add one or more songs to a playlist.

    Args:
        playlist_name: Target playlist name.
        track_queries: Comma-separated song searches.
        create_if_missing: True to create the playlist if it does not exist.
        max_matches_per_query: Number of matching tracks to add for each query, from 1 to 10.
    """
    if not playlist_name.strip():
        return "Music playlist name cannot be empty."
    queries = parse_csv_values(track_queries, max_items=100)
    if not queries:
        return "At least one track query is required."

    create_value = "true" if create_if_missing else "false"
    max_matches_per_query = _clamp(max_matches_per_query, 1, 10)

    script = f'''
    tell application "Music"
        set targetPlaylistName to "{escape_applescript_string(playlist_name)}"
        set shouldCreate to {create_value}
        {_playlist_lookup_script(playlist_name, playlist_collection="user playlists")}

        if targetPlaylist is missing value then
            if shouldCreate then
                set targetPlaylist to make new user playlist with properties {{name:targetPlaylistName}}
            else
                return "No matching Music playlist found."
            end if
        end if

        set trackQueries to {applescript_list(queries)}
        set addedCount to 0
        set missingOutput to ""

        repeat with queryItem in trackQueries
            set queryText to queryItem as text
            set foundTracks to (search library playlist 1 for queryText only songs)
            if (count of foundTracks) = 0 then
                set missingOutput to missingOutput & queryText & ", "
            else
                set perQueryCount to 0
                repeat with trackItem in foundTracks
                    if perQueryCount is less than {max_matches_per_query} then
                        try
                            duplicate trackItem to targetPlaylist
                            set addedCount to addedCount + 1
                            set perQueryCount to perQueryCount + 1
                        end try
                    end if
                end repeat
            end if
        end repeat

        set output to "Added " & addedCount & " tracks to Music playlist '" & name of targetPlaylist & "'."
        if missingOutput is not "" then set output to output & " Not found: " & missingOutput
        return output
    end tell
    '''
    return run_applescript(script)


@tool
def create_music_playlist_from_library(
    playlist_name: str,
    title_query: Optional[str] = "",
    artist: Optional[str] = "",
    album: Optional[str] = "",
    genre: Optional[str] = "",
    minimum_rating: int = 0,
    loved_only: bool = False,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    max_tracks: int = 50,
    replace_existing: bool = False,
) -> str:
    """
    Creates a rule-based Apple Music playlist from the user's local library.
    Call this tool when the user asks for a smart playlist based on artist, album, genre, title keywords, rating, loved tracks, or year range.
    This creates a normal static playlist populated from matching library tracks.

    Args:
        playlist_name: Playlist name.
        title_query: Optional text that must appear in the track title.
        artist: Optional artist filter.
        album: Optional album filter.
        genre: Optional genre filter.
        minimum_rating: Minimum Music rating from 0 to 100.
        loved_only: True to include only loved/favorite tracks.
        year_from: Optional minimum release year.
        year_to: Optional maximum release year.
        max_tracks: Maximum tracks to add, from 1 to 200.
        replace_existing: True to delete and recreate an existing playlist with the same name.
    """
    if not playlist_name.strip():
        return "Music playlist name cannot be empty."

    minimum_rating = _clamp(minimum_rating, 0, 100)
    max_tracks = _clamp(max_tracks, 1, 200)
    loved_value = "true" if loved_only else "false"
    replace_value = "true" if replace_existing else "false"
    year_from_value = year_from if year_from is not None else 0
    year_to_value = year_to if year_to is not None else 9999

    if year_from_value < 0 or year_to_value < 0 or year_to_value < year_from_value:
        return "Invalid year range."

    script = f'''
    tell application "Music"
        set newPlaylistName to "{escape_applescript_string(playlist_name)}"
        set titleFilter to "{escape_applescript_string(title_query)}"
        set artistFilter to "{escape_applescript_string(artist)}"
        set albumFilter to "{escape_applescript_string(album)}"
        set genreFilter to "{escape_applescript_string(genre)}"
        set minRating to {minimum_rating}
        set lovedOnly to {loved_value}
        set minYear to {year_from_value}
        set maxYear to {year_to_value}
        set shouldReplace to {replace_value}

        set existingPlaylists to (every user playlist whose name is newPlaylistName)
        if (count of existingPlaylists) > 0 then
            if shouldReplace then
                delete item 1 of existingPlaylists
            else
                return "A Music playlist named '" & newPlaylistName & "' already exists. Set replace_existing to true to replace it."
            end if
        end if

        set targetPlaylist to make new user playlist with properties {{name:newPlaylistName}}
        set addedCount to 0

        repeat with trackItem in tracks of library playlist 1
            set includeTrack to true

            if titleFilter is not "" then
                set trackName to ""
                try
                    set trackName to name of trackItem
                end try
                if trackName does not contain titleFilter then set includeTrack to false
            end if

            if artistFilter is not "" then
                set trackArtist to ""
                try
                    set trackArtist to artist of trackItem
                end try
                if trackArtist does not contain artistFilter then set includeTrack to false
            end if

            if albumFilter is not "" then
                set trackAlbum to ""
                try
                    set trackAlbum to album of trackItem
                end try
                if trackAlbum does not contain albumFilter then set includeTrack to false
            end if

            if genreFilter is not "" then
                set trackGenre to ""
                try
                    set trackGenre to genre of trackItem
                end try
                if trackGenre does not contain genreFilter then set includeTrack to false
            end if

            if minRating > 0 then
                set trackRating to 0
                try
                    set trackRating to rating of trackItem
                end try
                if trackRating < minRating then set includeTrack to false
            end if

            if lovedOnly then
                set trackLoved to false
                try
                    set trackLoved to loved of trackItem
                end try
                if trackLoved is false then set includeTrack to false
            end if

            if minYear > 0 or maxYear < 9999 then
                set trackYear to 0
                try
                    set trackYear to year of trackItem
                end try
                if trackYear < minYear or trackYear > maxYear then set includeTrack to false
            end if

            if includeTrack then
                try
                    duplicate trackItem to targetPlaylist
                    set addedCount to addedCount + 1
                end try
            end if

            if addedCount is greater than or equal to {max_tracks} then exit repeat
        end repeat

        return "Created Music playlist '" & newPlaylistName & "' with " & addedCount & " matching tracks."
    end tell
    '''
    return run_applescript(script)


@tool
def rate_current_music_track(rating: int, loved: Optional[bool] = None) -> str:
    """
    Rates or favorites the current Apple Music track.
    Call this tool when the user asks to rate the current song or mark it as loved/favorite.

    Args:
        rating: Star rating from 0 to 5. It is converted to Music's 0 to 100 rating scale.
        loved: Optional True to mark loved/favorite, False to unmark.
    """
    rating = _clamp(rating, 0, 5)
    music_rating = rating * 20
    loved_line = ""
    if loved is not None:
        loved_line = f"set loved of current track to {'true' if loved else 'false'}"

    script = f'''
    tell application "Music"
        if player state is stopped then return "No current Music track is playing."
        set rating of current track to {music_rating}
        {loved_line}
        return "Current Music track rated {rating} stars."
    end tell
    '''
    return run_applescript(script)


music_tools = [
    get_music_playback_status,
    control_music_playback,
    set_music_playback_options,
    search_music_library,
    play_music_track,
    list_music_playlists,
    play_music_playlist,
    play_music_recommendations,
    create_music_playlist,
    add_tracks_to_music_playlist,
    create_music_playlist_from_library,
    rate_current_music_track,
]
